import type { DomainId } from "./objects";

/**
 * Which book-and-period a model reading on screen belongs to.
 *
 * The rule set is identified by the book it was applied to AND the period it
 * was applied in: one domain has several releases and every release has many
 * periods, and "evaluable on this release" or "exposures scored" is a fact
 * about ONE of them. A reading fetched for another book or another period is
 * stale, not current, so the panel must not present it as the rule set that
 * produced what is on screen.
 *
 * `identity` is therefore `domain|period` — never a presentation string.
 * Passing a human sentence ("release · period · rule set") made the guard
 * compare a sentence against `domain|period`, which can never be equal, so
 * the model details page sat on "Reading the rule set…" for ever even though
 * the read had already come back. That is what this module exists to prevent:
 * the identity and the test for it are written once, in one place, and both
 * the page and the drill ask this module instead of re-deriving the string.
 */
export function modelIdentity(domain: DomainId | string, period: string): string {
  return `${domain}|${period}`;
}

/** The parts of a model reading that identify which book and period it is. */
export type ModelIdentified = { domain_id: string; period: string } | null;

/**
 * Is this reading the one the screen is asking for?
 *
 * An EMPTY requested period means "whatever period this release publishes
 * last": the address carries no period, the server picks one, and the reading
 * comes back stamped with it. Comparing the stamped period against the empty
 * request would fail for ever, so an empty request matches any period of the
 * requested book — and a non-empty request still has to match exactly.
 */
export function modelIsCurrent(model: ModelIdentified, identity: string): boolean {
  if (!model) return false;
  const cut = identity.indexOf("|");
  const domain = cut < 0 ? identity : identity.slice(0, cut);
  const period = cut < 0 ? "" : identity.slice(cut + 1);
  if (model.domain_id !== domain) return false;
  return period === "" || model.period === period;
}

/**
 * What the model details screen should show right now.
 *
 * Three states that look alike and are not: a read that failed is not a read
 * still running, and a read that landed for the PREVIOUS book is not this
 * book's rule set. "error" wins over "loading" so a failure is said out loud
 * rather than spinning, and a reading for another identity reads as loading
 * because another read is already on its way for the current one.
 */
export type ModelDisplayState = "loading" | "error" | "ready";

export function modelDisplayState(view: {
  model: ModelIdentified;
  identity: string;
  error: string;
}): ModelDisplayState {
  if (view.error) return "error";
  return modelIsCurrent(view.model, view.identity) ? "ready" : "loading";
}

/**
 * The address of the model details page for one book and period.
 *
 * Every link into the model details has to carry both, or the page opens on
 * the default book and the reader is shown the rule set of a book they were
 * not looking at. In v5 it is the Early Warning module's own route
 * (/early-warning/model, served from the EWS backend on 8501); it never
 * navigates into the frozen Cockpit.
 */
export function modelDetailHref(domain: DomainId | string, period: string): string {
  const query = new URLSearchParams({ domain: String(domain) });
  if (period) query.set("period", period);
  return `/early-warning/model?${query.toString()}`;
}
