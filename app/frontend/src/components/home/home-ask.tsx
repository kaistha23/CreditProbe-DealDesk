"use client";

/**
 * The Ask tab (PLAN_R13 Session H, R12_FEEDBACK J2): one centred, quiet chat box with "Ask Noor" above it, starter
 * prompts below, then small cards of recent work. Like a chat, not a dashboard.
 *
 * Every question is answered (J2 (b)): a scenario goes to What-If, a dashboard request to Lenses, a deal question to
 * Deal Desk, and everything else to the Cockpit engine through the Cockpit home's own `askFromHome` (unchanged), which
 * also hands auditor and regulator queries to the Cockpit queries flow. The book and the depth stay one click away
 * in the box's footer.
 *
 * Deal Desk edition: every question goes to Deal Desk's assistant (a new desk thread, as the Deal Desk home opens
 * one), except the CCO intelligence intents, which answer in place as before. The Cockpit's book switch and Deep
 * allowance are not offered, and the starters are Deal Desk's.
 */

import { memoIntent } from "@/lib/v5/thread-actions";
import * as React from "react";

import { withFrom } from "@/components/v5/ui/back-link-model"; // R14 U (K1)
import { useRouter } from "next/navigation";
import { ArrowUp, Loader2 } from "lucide-react";

import type { DomainAvailability, DomainId, RecentThread, RunMode } from "@/components/cockpit-v4/client";
import { domainEntry, domainNoun } from "@/components/cockpit-v4/domain-meta";
import { MicButton } from "@/components/noor/mic-button";
import { NoorMark } from "@/components/noor/noor-panel";
import { dispatch } from "@/components/noor/noor-dispatch";
import { ENGINE_LABEL, engineFor } from "@/components/noor/noor-route";
import { IntelAnswer } from "@/components/v5/intel/intel-panel";
import { type IntelMatch, routeIntel } from "@/lib/v5/intel-intents";
import { edition } from "@/lib/navigation";
import { cn } from "@/lib/utils";

import { RecentWork } from "./recent-work";
import { ASK_PLACEHOLDER, DEALDESK_ASK_PLACEHOLDER, DEALDESK_STARTERS, startersFor } from "./starters";

export interface HomeAskProps {
  domain: DomainId;
  domains: DomainAvailability | null;
  onDomain: (d: DomainId) => void;
  question: string;
  onQuestionChange: (q: string) => void;
  mode: RunMode;
  onModeChange: (m: RunMode) => void;
  /** The Cockpit home's own ask (frozen `askFromHome`): queries hand-off, then a Cockpit run. */
  onAsk: (text: string) => void;
  busy: boolean;
  askError: string;
  threads: RecentThread[] | null;
  onReopen: (t: RecentThread) => void;
  /** The Cockpit queries answers (auditor and regulator letters) render under the box. */
  queries?: React.ReactNode;
  onBrief: () => void;
}

export function HomeAsk(p: HomeAskProps) {
  const router = useRouter();
  const box = React.useRef<HTMLTextAreaElement | null>(null);
  const [routing, setRouting] = React.useState("");
  const [error, setError] = React.useState("");
  const [intel, setIntel] = React.useState<IntelMatch | null>(null);
  const noun = domainNoun(domainEntry(p.domains, p.domain));
  const dealdeskOnly = edition() === "dealdesk";
  const starters = dealdeskOnly ? [...DEALDESK_STARTERS] : startersFor(p.domain, noun);
  const busy = p.busy || Boolean(routing);

  React.useEffect(() => { box.current?.focus(); }, []);
  // The box grows with the question, up to six lines.
  React.useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [p.question]);

  const ask = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setError("");
    // R13 M (§I): a question one of the CCO intelligence engines finishes is answered here, with its panel.
    const hit = routeIntel(q);
    if (hit) { setIntel(hit); return; }
    setIntel(null);
    const engine = dealdeskOnly ? "dealdesk" : engineFor(q);
    // R16 t (M7): a memo request needs an answer to write up; with its question it opens a thread that writes it
    const mi = memoIntent(q);
    if (mi && !mi.question) {
      setError(`Ask your question first, then ask for the ${mi.kind} in its thread; or type it in one go, e.g. “write a ${mi.kind} on which borrowers moved into Stage 2”.`);
      return;
    }
    if (engine === "cockpit" && !mi) { p.onAsk(q); return; }
    setRouting(ENGINE_LABEL[engine]);
    try {
      const out = await dispatch(engine, q, { domain: p.domain, mode: p.mode });
      router.push(withFrom(out.href, "ask", "/?tab=ask")); // R14 U (K1): the module shows "← Back to Ask"
    } catch (e) {
      setRouting("");
      setError(e instanceof Error ? e.message : `${ENGINE_LABEL[engine]} could not open that just now.`);
    }
  };

  const books = (p.domains?.domains ?? []).filter((d) => d.ready);
  return (
    <div className="mx-auto w-full max-w-[46rem] pt-10 sm:pt-16" data-testid="home-ask" data-tour="ask-box">
      <div className="flex flex-col items-center text-center">
        <NoorMark className="size-10 [&_svg]:size-5" />
        <h2 className="mt-4 font-prose text-[30px] leading-tight tracking-[-0.015em] text-text-primary" data-testid="home-ask-title">
          Ask Noor</h2>
      </div>

      <form className="mt-7 rounded-2xl border border-border bg-surface shadow-[0_1px_2px_rgba(0,0,0,0.04),0_8px_24px_-12px_rgba(0,0,0,0.12)] transition-colors focus-within:border-accent/60"
            data-testid="cockpit-v4-ask-box"
            onSubmit={(e) => { e.preventDefault(); void ask(p.question); }}>
        <label className="sr-only" htmlFor="home-ask-input">Ask Noor</label>
        <textarea id="home-ask-input" ref={box} rows={1} dir="auto" value={p.question}
                  // The box shows focus itself (its border); the global focus ring would draw a second frame inside it.
                  style={{ outline: "none" }}
                  data-testid="cockpit-v4-question"
                  onChange={(e) => p.onQuestionChange(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(p.question); } }}
                  placeholder={dealdeskOnly ? DEALDESK_ASK_PLACEHOLDER : ASK_PLACEHOLDER}
                  className="block w-full resize-none bg-transparent px-5 pb-2 pt-4 font-user text-[15.5px] leading-relaxed text-text-primary outline-none placeholder:text-text-muted" />
        <div className="flex items-center gap-3 px-3 pb-3 pl-5">
          {books.length > 1 && !dealdeskOnly ? (
            <div role="group" aria-label="Book" className="flex items-center gap-0.5 text-[12px]" data-testid="domain-switch" data-domain={p.domain}>
              {books.map((b) => (
                <button key={b.domain_id} type="button" aria-pressed={b.domain_id === p.domain} data-testid={`domain-${b.domain_id}`}
                        onClick={() => p.onDomain(b.domain_id)}
                        className={cn("rounded-md px-2 py-0.5 font-medium transition-colors",
                          b.domain_id === p.domain ? "bg-surface-sunken text-text-primary" : "text-text-muted hover:text-text-primary")}>
                  {b.domain_label.replace(/ Credit$/, "")}
                </button>
              ))}
            </div>
          ) : null}
          {dealdeskOnly ? null : (
          <label className="flex items-center gap-1.5 text-[12px] text-text-muted" title="Deep gives the Cockpit a longer allowance, for work that needs it">
            <input type="checkbox" checked={p.mode === "deep"} data-testid="cockpit-v4-mode-deep"
                   onChange={(e) => p.onModeChange(e.target.checked ? "deep" : "standard")} className="accent-accent" />
            Deep
          </label>)}
          {/* R14 n (K10): ask by voice; the transcript shows in the box before sending. */}
          <MicButton value={p.question} onChange={p.onQuestionChange} size="md" testId="home-ask-mic" className="ml-auto" />
          <button type="submit" disabled={busy || !p.question.trim()} aria-label="Ask" data-testid="cockpit-v4-ask"
                  className="flex size-8 items-center justify-center rounded-full bg-accent text-accent-contrast transition-opacity hover:bg-accent-hover disabled:opacity-30">
            {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <ArrowUp className="size-4" aria-hidden />}
          </button>
        </div>
      </form>

      {routing ? <p className="mt-3 text-center text-[12.5px] text-text-muted" role="status">Opening it in {routing}…</p> : null}
      {error || p.askError ? (
        <p className="mt-3 text-center text-[13px] text-negative" role="alert" data-testid="cockpit-v4-submit-error">{error || p.askError}</p>
      ) : null}

      {intel ? (
        <div className="mt-5" data-testid="home-ask-intel">
          <IntelAnswer m={intel} onClose={() => setIntel(null)} onDeal={(d) => setIntel({ ...intel, deal: d, missing: undefined })} />
        </div>) : null}

      <div className="mt-5 flex flex-wrap justify-center gap-2" data-testid="cockpit-v4-prompts">
        {starters.map((s) => (
          <button key={s} type="button" disabled={busy} data-testid="cockpit-v4-prompt"
                  onClick={() => { p.onQuestionChange(s); void ask(s); }}
                  className="rounded-full border border-border bg-surface px-3.5 py-1.5 text-[12.5px] text-text-secondary transition-colors hover:border-border-strong hover:text-text-primary disabled:opacity-40">
            {s}
          </button>
        ))}
      </div>

      {p.queries ? <div className="mt-6 text-left">{p.queries}</div> : null}

      <p className="mt-6 text-center text-[11.5px] text-text-muted" data-testid="cockpit-v4-trace-note">
        Every answer carries a Trace: each figure is bound to a query that actually ran.{" "}
        <button type="button" onClick={p.onBrief} className="font-medium underline-offset-4 hover:text-text-primary hover:underline">
          Today&apos;s brief</button>
      </p>

      <div className="mt-12">
        <RecentWork threads={p.threads} onReopen={p.onReopen} domain={p.domain} />
      </div>
    </div>
  );
}
