/**
 * R11 Session K: which scope the Monitoring agent panel opens on, and which tab a link asks for (pure, unit tested).
 *
 * A lens the agent built (template key `monitor:<scope>`) opens its set's own scope: the book and segment filters, or
 * the lens the set was planned for (`monitor:lens:<id>`). Any other lens is a scope of its own (its filters and KPIs).
 */
export type MonitorScope = { lensId?: string; book?: "corporate" | "retail"; filters?: { dim: string; values: string[] }[] };
export type MonitorTab = "proposed" | "active" | "alerts";

export function monitorScopeOf(lens: { lens_id: string; book: "corporate" | "retail"; template_key?: string;
                                       spec: { filters?: { dim: string; values: string[] }[] } }): MonitorScope {
  const key = lens.template_key ?? "";
  if (key.startsWith("monitor:lens:")) return { lensId: key.slice("monitor:lens:".length) };
  if (key.startsWith("monitor:")) return { book: lens.book, filters: lens.spec.filters ?? [] };
  return { lensId: lens.lens_id };
}

/** `?monitor=alerts` (the notification link) opens the panel on that tab; any other value opens it on Proposed. */
export function monitorTabOf(v: string | null): MonitorTab | undefined {
  if (v === "alerts" || v === "active" || v === "proposed") return v;
  return v ? "proposed" : undefined;
}

/** The query string of the panel's GET for a scope. */
export function scopeQuery(s: MonitorScope): string {
  const p = new URLSearchParams();
  if (s.lensId) p.set("lens_id", s.lensId);
  else {
    p.set("book", s.book ?? "corporate");
    p.set("filters", JSON.stringify(s.filters ?? []));
  }
  return p.toString();
}
