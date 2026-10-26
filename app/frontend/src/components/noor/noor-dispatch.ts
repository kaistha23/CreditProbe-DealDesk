"use client";

/**
 * Sending a routed question to its engine (R13 H, J2 (b)). The engines are the existing ones, called through their own
 * clients, unchanged:
 *
 *   cockpit   the Cockpit run API (`startRun`), which opens the conversation at /cockpit/thread/<id>; an auditor or
 *             regulator query goes to the Ask tab instead, where the Cockpit's own queries hand-off answers it
 *   whatif    What-If `createThread({question})`, then /what-if/thread/<id>
 *   lenses    Lenses `create({request})`, then /lenses/<id>
 *   dealdesk  a NEW Deal Desk thread (R14 n, K16), /deal-desk/thread/<id>, which asks `?q=` exactly once
 *
 * Returns where the reader goes; the caller navigates (the panel keeps itself open).
 */

import { rememberRun as rememberCockpitRun, startRun, type DomainId, type RunMode } from "@/components/cockpit-v4/client";
import { isQueryQuestion } from "@/lib/v5/cockpit-queries";
import { dealdesk } from "@/lib/v5/dealdesk";
import { deskThreadHref, startFresh } from "@/lib/v5/thread-rule";
import { lenses } from "@/lib/v5/lenses";
import { rememberRun as rememberWhatIfRun, whatif } from "@/lib/v5/whatif";
import { landingQuestion, rememberPendingMemo } from "@/lib/v5/thread-actions-pending";

import { edition } from "@/lib/navigation";

import type { Engine } from "./noor-route";

export interface Dispatched { engine: Exclude<Engine, "brief">; href: string }

/** Deal Desk edition: the Cockpit, What-If and Lenses engines are not in the product; every question is Deal Desk's. */
export function engineInEdition(engine: Exclude<Engine, "brief">): Exclude<Engine, "brief"> {
  return edition() === "dealdesk" ? "dealdesk" : engine;
}

export async function dispatch(requested: Exclude<Engine, "brief">, question: string,
                               opts: { domain?: DomainId; mode?: RunMode } = {}): Promise<Dispatched> {
  const engine = engineInEdition(requested);
  const domain: DomainId = opts.domain === "retail" ? "retail" : "corporate";
  const typed = question.trim();
  // R16 t (M7): "prepare a memo on X" asks X in the new thread; the thread then writes the Word document. Deal Desk's
  // thread page reads the whole request itself (it asks ?q= through its own memo rule).
  const lq = engine === "dealdesk" ? { ask: typed, memo: null } : landingQuestion(typed);
  const q = lq.ask;
  if (engine === "whatif") {
    const t = await whatif.createThread(startFresh("whatif", { domain, question: q }));  // R16 m (M6): always a new thread
    if (t.run) rememberWhatIfRun(t.thread_id, t.run.run_id);
    if (lq.memo) rememberPendingMemo("whatif", t.thread_id, lq.memo);
    return { engine, href: `/what-if/thread/${encodeURIComponent(t.thread_id)}` };
  }
  if (engine === "lenses") {
    const out = await lenses.create(startFresh("lenses", { request: q, book: domain }));
    if (lq.memo && out.thread_id) rememberPendingMemo("lenses", out.thread_id, lq.memo);
    return { engine, href: `/lenses/${encodeURIComponent(out.lens.lens_id)}` };
  }
  if (engine === "dealdesk") {
    try {
      const t = await dealdesk.newDeskThread(q);
      return { engine, href: deskThreadHref(t.thread_id, q) };
    } catch {
      return { engine, href: deskThreadHref("new", q) };
    }
  }
  if (isQueryQuestion(q)) {
    return { engine, href: `/?tab=ask&q=${encodeURIComponent(q)}` };
  }
  const started = await startRun(startFresh("cockpit", { question: q, mode: opts.mode ?? "standard", domain }));
  rememberCockpitRun({ runId: started.run_id, threadId: started.thread_id, cursor: 0, question: q });
  if (lq.memo) rememberPendingMemo("cockpit", started.thread_id, lq.memo);
  return { engine, href: `/cockpit/thread/${encodeURIComponent(started.thread_id)}` };
}
