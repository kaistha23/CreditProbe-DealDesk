"use client";

/**
 * The Cockpit landing page, as it exists in a V4 runtime.
 *
 * The LAYOUT is the earlier Cockpit's, restored deliberately: a greeting, one
 * wide question box across the workspace, business prompts beneath it, the
 * trace line, then what requires attention and what moved in ECL, then the
 * conversations you can pick back up. That page read like an executive
 * workspace and the narrow centred column did not.
 *
 * The BACKEND is entirely V4 and nothing of the old one came back with the
 * look. `/investigations`, `/agentic/officer`, `/ask/mode`, `/ask/briefing`,
 * `/ask/suggestions` and the V2/V3 diagnostics are not reached from this page
 * — not shimmed, not translated, not caught: never called. The attention
 * sections are the deterministic V4 engine, the drawer is the V4 drawer, and
 * Investigate Further seeds a real V4 thread.
 *
 * A separate component rather than a branch inside the legacy page, because
 * React runs every hook a component declares: guarding the JSX would not stop
 * the legacy Cockpit's requests, and not instantiating it does.
 */

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { useWideContent } from "@/components/layout/content-width";

import { AttentionDrawer } from "./attention-drawer";
import { InboxPanel } from "./inbox-panel";
import { EclPanel } from "./ecl-panel";
import { recallDomain, rememberDomain } from "./domain-switch";
import {
  rememberInvestigation,
  type AttentionItem,
  type RecentThread,
} from "./client";
import { AttentionDeepLink } from "@/components/v5/attention/drawer-extras";

import {
  readAttentionItem,
  rememberRun,
  startRun,
  readDomains,
  type DomainAvailability,
  type DomainId,
  type RunMode,
} from "./client";
import { useSession } from "./continue-where-you-left-off";
import { CockpitGreeting } from "@/components/v5/core/greeting";
import { CockpitQueries, useCockpitQueries } from "@/components/v5/queries/cockpit";
import { HomeTabs } from "@/components/home/home-tabs";

export function CockpitV4Home() {
  const searchParams = useSearchParams();
  const initialQuestion = searchParams.get("q") ?? "";
  // Operator detail is opt-in through the URL so a demonstration does not
  // show model ids and request sizes on a shared screen by default.
  const operatorView = searchParams.get("operator") === "1";

  const router = useRouter();
  const { name, threads, ready, refresh } = useSession();
  const [open, setOpen] = React.useState<AttentionItem | null>(null);
  const [question, setQuestion] = React.useState(initialQuestion);
  const [mode, setMode] = React.useState<RunMode>("standard");
  const [opening, setOpening] = React.useState(false);
  const [askError, setAskError] = React.useState("");
  // FX-R10-Q1: auditor and regulator queries are answered here (components/v5/queries/cockpit.tsx).
  const v5q = useCockpitQueries();
  // Which book Home is showing. Read once from the server, so a runtime with
  // one domain unpublished disables that control and says why rather than
  // offering a switch that cannot work.
  const [domains, setDomains] =
    React.useState<DomainAvailability | null>(null);
  const [domain, setDomain] = React.useState<DomainId>("corporate");

  React.useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const available = await readDomains();
        if (!live) return;
        setDomains(available);
        const remembered = recallDomain();
        const usable = remembered && available.ready.includes(remembered)
          ? remembered
          : available.default_domain;
        setDomain(usable);
      } catch {
        // A runtime that cannot answer which books it has still answers
        // questions about the default one.
      }
    })();
    return () => {
      live = false;
    };
  }, []);

  const chooseDomain = React.useCallback((next: DomainId) => {
    setDomain(next);
    rememberDomain(next);
  }, []);

  /**
   * Asking from the home page opens a CONVERSATION.
   *
   * It does not answer here. A page that rendered the answer in place would
   * make the second question feel like starting over, which is exactly what
   * the old experience got right and this one had lost: the answer is never
   * the end, the follow-up is.
   *
   * The question travels in the URL rather than in component state, so a
   * refresh between opening the thread and the first answer does not lose
   * it -- and the thread asks it exactly once.
   */
  const openThread = React.useCallback(
    (threadId: string) => {
      router.push(`/cockpit/thread/${encodeURIComponent(threadId)}`);
    },
    [router],
  );

  const askFromHome = React.useCallback(
    async (text: string) => {
      const asked = text.trim();
      if (!asked || opening) return;
      if (v5q.claims(asked) && (await v5q.ask(asked))) return;
      setOpening(true);
      setAskError("");
      try {
        // The run creates its own thread, pinned to the selected book.
        //
        // It used to create the thread first and then start a run in it,
        // which quietly discarded the domain: `startRun` reads it only when
        // OPENING a conversation, so a retail question would have opened a
        // corporate thread and read corporate relations. Asking the run to
        // make the thread is what keeps the selection and the evidence the
        // same decision.
        //
        // The run also STARTS here, before the navigation, so the question
        // never reaches the URL and a reload cannot ask it a second time --
        // the thread finds a run already going and follows it.
        const started = await startRun({
          question: asked, mode, domain,
        });
        rememberRun({
          runId: started.run_id, threadId: started.thread_id, cursor: 0,
          question: asked,
        });
        openThread(started.thread_id);
      } catch (cause) {
        setOpening(false);
        setAskError(
          cause instanceof Error
            ? cause.message
            : "The conversation could not be opened.",
        );
      }
    },
    [opening, openThread, domain, mode, v5q],
  );
  /** Reopen a real persisted thread: its own page, with its own transcript. */
  const reopen = React.useCallback(
    (thread: RecentThread) => {
      // §18, §51. A conversation belongs to ONE book, and reopening it puts
      // the reader back in that book. Without this they land in whatever
      // the switch happened to be showing, and their next question in the
      // thread is refused for a reason that has nothing to do with what
      // they typed -- the thread's domain wins, correctly, and the refusal
      // is the first they hear of it.
      if (thread.domain_id && thread.domain_id !== domain) {
        setDomain(thread.domain_id);
        rememberDomain(thread.domain_id);
      }
      return openThread(thread.thread_id);
    },
    [domain, openThread],
  );

  // Two dashboards, wide tables and a chat column: this page IS the
  // width. Every other page keeps the shell default.
  useWideContent();

  return (
    <div
      // A 1728px display was rendering a 1024px ribbon with two empty
      // thirds. The page now takes the workspace it is given up to
      // 1440px; answer PROSE still wraps at 68ch inside it, which is
      // where readability actually lives, while the dashboards and
      // tables get the width they were starved of.
      className="mx-auto w-full max-w-[90rem] px-4 py-10 sm:px-6 lg:px-10"
      data-testid="cockpit-v4-home"
    >
      {/* FX-R13-01 (PLAN_R13 Session H): two tabs, Brief (Noor's brief, first) and Ask (one centred box), drawn by
          components/home/home-tabs.tsx. The attention cards are not a panel here: they are the evidence a brief
          line's Why opens, in the drawer below. */}
      <HomeTabs
        greeting={<CockpitGreeting fallbackName={name} />}
        domain={domain} domains={domains} onDomain={chooseDomain}
        question={question} onQuestionChange={setQuestion} mode={mode} onModeChange={setMode}
        onAsk={(text) => void askFromHome(text)} busy={opening} askError={askError}
        threads={ready ? threads : null} onReopen={(thread) => void reopen(thread)}
        queries={<CockpitQueries state={v5q} attach={false} />}
        onEvidence={(id) => void readAttentionItem(id).then(({ item }) => setOpen(item), () => undefined)}
        more={(
          <>
            <EclPanel domain={domain} />
            <div>
              <h2 className="text-sm font-semibold text-text-primary">Sent to you</h2>
              <div className="mt-2"><InboxPanel /></div>
            </div>
          </>
        )}
      />

      <AttentionDeepLink attention={searchParams.get("attention")} onOpen={setOpen} onDomain={chooseDomain}
                         readItem={readAttentionItem} />

      <AttentionDrawer
        item={open}
        operatorView={operatorView}
        onClose={() => setOpen(null)}
        onInvestigate={(started) => {
          // §9: an investigation OPENS. The seed is already on the thread
          // server-side; what was missing was the reader ever arriving
          // somewhere that looked like an investigation had begun.
          rememberInvestigation({
            threadId: started.threadId,
            itemId: started.item.item_id,
            suggested: started.suggested,
          });
          setOpen(null);
          openThread(started.threadId);
        }}
      />
    </div>
  );
}
