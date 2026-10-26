/**
 * R15 L6 (pure, tested): what an agent finding row opens. Every agent result page (Early Warning triage, What-If,
 * Lenses, Deal Desk agents) uses the same rules:
 *
 *   findingSubject(f)          the customer a finding is about (borrower_id / obligor_id / customer_id), or null
 *   ewsDetailHref(id, …)       the Early Warning borrower card, filtered to that customer, with a back link
 *   b360LinkFor(id, …)         Borrower 360 (corporate CB ids only), with from= and the exact back path (K1/K11)
 *   backWithRun(here, runId)   the page the drawer sits on, with agent_run=<id> so Back reopens the same run
 *   originFor(agent)           the back-link origin key of the agent's module
 *   splitIds(text)             a narrative split into text and borrower ids (names in the answer are clickable)
 *   sourceLegend(sid, …)       the hover legend of an S-chip: "S3: Borrower 360 facts"
 */
import { withFrom } from "../ui/back-link-model.ts";
import { b360Href, hasBorrower360 } from "../ui/borrower-360-model.ts";
import { edition } from "../../../lib/navigation.ts";

export interface FindingLike { data?: Record<string, unknown> | null; kind?: string }

export interface Subject { id: string; name: string; domain: "corporate" | "retail"; period: string }

const ID_KEYS = ["borrower_id", "obligor_id", "customer_id"] as const;

export function findingSubject(f: FindingLike | null | undefined, ctx?: { domain?: unknown; period?: unknown }): Subject | null {
  const d = (f?.data ?? {}) as Record<string, unknown>;
  const id = ID_KEYS.map((k) => d[k]).find((v) => typeof v === "string" && v.trim()) as string | undefined;
  if (!id) return null;
  const name = String(d.borrower_name ?? d.obligor_name ?? d.customer_name ?? d.name ?? id);
  const domain = /^RC\d/i.test(id) || ctx?.domain === "retail" ? "retail" : "corporate";
  const ews = (d.ews ?? {}) as Record<string, unknown>;
  const period = String(ews.period ?? d.period ?? ctx?.period ?? "");
  return { id: id.trim(), name, domain, period };
}

export function originFor(agent: string | null | undefined): string {
  const a = (agent ?? "").split(".")[0];
  return a === "ews" ? "ews" : a === "whatif" ? "whatif" : a === "lenses" ? "lenses" : a === "dealdesk" ? "deal-desk" : "drawer";
}

/** The page the drawer is on, with agent_run=<id> (replacing any earlier one) so Back reopens this run. */
export function backWithRun(here: string, runId: string): string {
  const at = here.indexOf("?");
  const path = at >= 0 ? here.slice(0, at) : here;
  const sp = new URLSearchParams(at >= 0 ? here.slice(at + 1) : "");
  sp.delete("from");
  sp.delete("back");
  if (runId) sp.set("agent_run", runId);
  const q = sp.toString();
  return `${path}${q ? `?${q}` : ""}`;
}

export function ewsDetailHref(s: Subject, origin: string, back: string): string {
  // Deal Desk edition: no Early Warning screen; the finding's customer opens in Deal Desk's customer files.
  if (edition() === "dealdesk") return withFrom(`/deal-desk/customer-packs?cif=${encodeURIComponent(s.id)}`, origin, back);
  const q = new URLSearchParams({ domain: s.domain, customer: s.id });
  if (/^\d{4}Q[1-4]$/i.test(s.period)) q.set("period", s.period.toUpperCase());
  const href = `/early-warning?${q.toString()}`;
  // inside Early Warning the back path is the page itself; from another module it is that module
  return withFrom(href, origin === "ews" ? "ews" : origin, back);
}

export function b360LinkFor(s: Subject, origin: string, back: string): string | null {
  if (!hasBorrower360(s.id)) return null;
  return withFrom(b360Href(s.id, s.period), origin, back);
}

/** Text split into plain parts and borrower ids (CB00123 corporate, RC0012345 retail). */
export function splitIds(text: string): { text?: string; id?: string }[] {
  const out: { text?: string; id?: string }[] = [];
  const re = /\b(CB\d{4,6}|RC\d{5,7})\b/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push({ text: text.slice(last, m.index) });
    out.push({ id: m[1] });
    last = m.index + m[1].length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out;
}

export function sourceLegend(sid: string, sources: Record<string, string> | null | undefined, tool?: string): string {
  const what = sources?.[sid] ?? (tool ? tool.replace(/^(dd|ews|wi|whatif|lens|lenses)_/, "").replace(/_/g, " ") : "");
  return what ? `${sid}: ${what} (opens the step that read it)` : `${sid}: opens the step that read it`;
}

/** Seconds since `startMs`, and whether planning has gone on too long (L4: 60 s). */
export function planningState(startMs: number, nowMs: number, hasSteps: boolean, finished: boolean, limitS = 60):
  { seconds: number; stalled: boolean } {
  const seconds = Math.max(0, Math.round((nowMs - startMs) / 1000));
  return { seconds, stalled: !finished && !hasSteps && seconds >= limitS };
}

/** Verdict words spelled out (UTP / SICR on first use). */
export const VERDICT_PLAIN: Record<string, string> = {
  utp: "Unlikely to pay (UTP) → Stage 3",
  sicr: "Significant increase in credit risk (SICR) → Stage 2",
  watchlist: "Watchlist (no stage move)",
  watch: "Watch",
  noise: "Noise (explained)",
};
