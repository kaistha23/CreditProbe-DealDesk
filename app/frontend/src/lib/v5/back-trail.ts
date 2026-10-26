/**
 * R7: where Back goes, decided in one place (no React, so it is unit-tested).
 *
 * Back means the exact previous screen and step: the previous entry in this tab's history, when that entry is
 * this app and not the sign-in page. With no such entry (a new tab, a pasted link, a refresh straight onto a
 * deep page), Back goes to the `returnTo` the link carried, else to the screen's own parent.
 *
 * The previous entry is read from the Navigation API where the browser has it (same-origin entries only).
 * Elsewhere an in-memory trail of the URLs this tab has shown since its last full load stands in for it.
 */

/** Pages Back never returns to. */
export function isSkippable(url: string): boolean {
  const path = url.replace(/^https?:\/\/[^/]+/, "").split(/[?#]/)[0];
  return path === "/login" || path.startsWith("/login/");
}

/**
 * The previous entry from the Navigation API's entries: the nearest earlier entry whose URL differs from the
 * current one (a reload or a link to the page you are on adds a duplicate entry, which Back skips), with how many
 * entries back it is. Null when there is none, or when it is the sign-in page.
 */
export function previousFromEntries(urls: (string | null | undefined)[], index: number): { url: string; delta: number } | null {
  const here = urls[index];
  for (let j = index - 1; j >= 0; j--) {
    const u = urls[j];
    if (!u) return null;
    if (u === here) continue;
    return isSkippable(u) ? null : { url: u, delta: index - j };
  }
  return null;
}

/** The in-memory trail (module scope: empty again after a full load). */
const trail: string[] = [];

/**
 * Record a URL the app shows. A push adds it. Going back to the URL before the current one pops the current one.
 * A replace is recorded with `replace: true`, so it overwrites the current entry, as the browser history does.
 */
export function recordVisit(url: string, replace = false): void {
  if (isSkippable(url)) return;
  const n = trail.length;
  if (n && trail[n - 1] === url) return;
  if (n > 1 && trail[n - 2] === url) { trail.pop(); return; }
  if (replace && n) trail[n - 1] = url;
  else trail.push(url);
  if (trail.length > 100) trail.shift();
}

export function previousFromTrail(): { url: string; delta: number } | null {
  return trail.length > 1 ? { url: trail[trail.length - 2], delta: 1 } : null;
}

/** For tests. */
export function resetTrail(): void { trail.length = 0; }

/** The previous in-app entry of this tab (and how many history entries back it is), or null. */
export function previousInApp(): { url: string; delta: number } | null {
  if (typeof window === "undefined") return null;
  const nav = (window as unknown as {
    navigation?: { currentEntry?: { index: number } | null; entries?: () => { url: string | null }[] };
  }).navigation;
  if (nav?.entries && nav.currentEntry) {
    return previousFromEntries(nav.entries().map((e) => e.url), nav.currentEntry.index);
  }
  return previousFromTrail();
}
