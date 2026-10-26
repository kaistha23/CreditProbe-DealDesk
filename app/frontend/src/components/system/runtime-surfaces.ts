/**
 * Reading a partial runtime out of a health payload.
 *
 * A backend can be entirely healthy and still not serve every route the shell
 * knows about. The Cockpit V4 API is exactly that: it answers Cockpit
 * questions and does not carry the landing-page widgets, which live in the
 * main backend. Reporting that as "Backend offline" is a lie, and reporting it
 * as "All systems operational" hides why half the page is empty.
 *
 * These functions read only what the payload DECLARES (`data.optional`), so a
 * backend that declares nothing — every CreditProbe instance that exists
 * today — takes the `null` branch and behaves exactly as it did before.
 *
 * Kept out of the component file so it can be imported by the project's test
 * runner, which strips types from `.ts` and cannot parse JSX.
 */

import type { ComponentHealth, HealthResponse } from "@/lib/api";

/** The optional surfaces this backend says it is not currently serving. */
export function optionalSurfaces(health: HealthResponse): {
  runtime: string;
  absent: ComponentHealth[];
} | null {
  const absent = health.components.filter(
    (c) => c.data?.optional === true && c.status !== "ok",
  );
  if (absent.length === 0) return null;
  const runtime = absent
    .map((c) => (typeof c.data?.runtime === "string" ? c.data.runtime : ""))
    .find(Boolean);
  return runtime ? { runtime, absent } : null;
}

/**
 * A label for a runtime that serves part of the product, or `null`.
 *
 * The one optional surface any backend declares today is the legacy
 * dashboard API, which the Cockpit V4 API does not carry. In v5 that is not a
 * gap: the dashboards are the v5 modules' own services, so the header says
 * nothing about it (PLAN_R4 G1: no runtime or provenance notes on screen).
 * The reading of the payload stays in `optionalSurfaces` for the status page.
 */
export function partialRuntimeLabel(health: HealthResponse): string | null {
  void health;
  return null;
}
