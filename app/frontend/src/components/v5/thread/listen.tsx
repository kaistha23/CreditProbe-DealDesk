"use client";

/**
 * R16 n: **Listen** on every answer (it sits in the shared thread action bar, so every module has it).
 *
 * A click reads the answer as rendered (`domBlocks` + the chart and table on screen, `narration-dom.ts`), writes the
 * spoken narration (`lib/v5/narration.ts`: headline, the numbers that matter, where to look, the next step) and plays
 * it line by line in the reader's chosen voice for the answer's language (Settings → Voice; neural or browser, male or
 * female as chosen). While a line points at a bar or a row, that element pulses. A second click stops. Nothing plays
 * unless clicked (R16 M1): no timers, no autoplay; with no voice chosen it says so and stays silent.
 */

import * as React from "react";
import { Square, Volume2 } from "lucide-react";

import { CHOOSE_VOICE_NOTE, VOICE_SETTINGS_HREF, speakText, stopSpeech } from "@/components/noor/noor-voice";
import { chosenVoiceFor } from "@/components/noor/noor-store";
import { type ModuleKey, type DomLike, domBlocks } from "@/lib/v5/thread-actions";
import { type Narration, answerLang, narrate } from "@/lib/v5/narration";
import { cn } from "@/lib/utils";

import { readVisuals, targetElement } from "./narration-dom";

const PULSE = "cp-narrate-pulse";
const HOST = "cp-narrate-host";

/** One narration plays at a time, across the page. */
let current: { id: number; stop: () => void } | null = null;
let seq = 0;

export function stopListening(): void { current?.stop(); }

/** The answer's narration, as Listen would say it (used by the walk and by tests in the browser). */
export function narrationFor(module: ModuleKey, question: string, el: Element | null, nearby = false): { narration: Narration; visuals: ReturnType<typeof readVisuals> } {
  const blocks = domBlocks(el as unknown as DomLike | null);
  let visuals = readVisuals(el);
  // A panel's chart or table may sit in the card beside its summary: look up to three levels out, inside the page.
  for (let up = el?.parentElement ?? null, i = 0; nearby && up && i < 3 && !visuals.charts.length && !visuals.tables.length; up = up.parentElement, i += 1) {
    if (up.tagName === "MAIN" || up.tagName === "BODY") break;
    visuals = readVisuals(up);
  }
  const words = blocks.map((b) => (b.kind === "text" ? b.text : b.kind === "bullets" ? b.items.join(" ") : "")).join(" ");
  const narration = narrate({ module, question, lang: answerLang(words), blocks,
                              charts: visuals.charts.map((c) => c.facts), tables: visuals.tables.map((t) => t.facts) });
  return { narration, visuals };
}

const btn = "inline-flex h-7 items-center gap-1 rounded-md px-2 text-[11.5px] text-text-secondary hover:bg-surface-hover hover:text-text-primary disabled:opacity-40";

export function ListenButton({ module, question, getEl, compact, testId, nearby = false }: {
  module: ModuleKey; question: string;
  /** A panel: its chart or table may be in the card next to it. */
  nearby?: boolean;
  /** The answer element (its words, chart and table). */
  getEl: () => Element | null;
  compact?: boolean; testId: string;
}) {
  const [state, setState] = React.useState<"idle" | "playing">("idle");
  const [line, setLine] = React.useState("");
  const [note, setNote] = React.useState("");
  const [said, setSaid] = React.useState("");
  const mine = React.useRef(0);
  React.useEffect(() => () => { if (current && current.id === mine.current) current.stop(); }, []);

  const click = async () => {
    if (state === "playing" && current?.id === mine.current) { current.stop(); return; }
    current?.stop();
    setNote("");
    const el = getEl();
    const { narration, visuals } = narrationFor(module, question, el, nearby);
    setSaid(narration.text);
    const lang = narration.lang === "ar" ? "ar-gulf" : "en";
    const choice = chosenVoiceFor(lang);
    if (!choice) { setNote(CHOOSE_VOICE_NOTE); return; }
    const id = ++seq;
    mine.current = id;
    let stopped = false;
    let lit: { el: Element; host: Element } | null = null;
    const unlight = () => { if (lit) { lit.el.classList.remove(PULSE); lit.host.classList.remove(HOST); lit = null; } };
    const stop = () => { stopped = true; stopSpeech(); unlight(); setState("idle"); setLine(""); if (current?.id === id) current = null; };
    current = { id, stop };
    setState("playing");
    for (const seg of narration.segments) {
      if (stopped) return;
      unlight();
      const t = targetElement(visuals, seg.target);
      if (t) {
        lit = t;
        t.host.classList.add(HOST);
        t.el.classList.add(PULSE);
        try { (t.host as HTMLElement).scrollIntoView?.({ block: "nearest", behavior: "smooth" }); } catch { /* ignore */ }
      }
      setLine(seg.text);
      const r = await new Promise<{ ok: boolean; note?: string }>((ok) => {
        let done = false;
        const fin = (v: { ok: boolean; note?: string }) => { if (!done) { done = true; ok(v); } };
        void speakText(seg.text, lang, "male", { end: () => fin({ ok: true }) }, choice).then((x) => {
          if (x.note) setNote(x.note);
          if (!x.spoken) fin({ ok: false, note: x.state === "not-chosen" ? CHOOSE_VOICE_NOTE : x.note });
          else if (x.state !== "speaking") fin({ ok: true });   // the neural voice resolves when the line is over
        }).catch(() => fin({ ok: false }));
      });
      if (!r.ok) { if (r.note) setNote(r.note); break; }
      if (!stopped) await new Promise((ok) => setTimeout(ok, 180));
    }
    if (!stopped) stop();
  };

  return (
    <>
      <button type="button" className={cn(btn, state === "playing" && "text-accent")} onClick={() => void click()} aria-pressed={state === "playing"}
              data-testid={`${testId}-listen`} data-state={state} data-narration={said || undefined}
              title={state === "playing" ? "Stop" : "Listen: a short spoken summary that points you to the chart and table"}>
        {state === "playing" ? <Square size={11} aria-hidden /> : <Volume2 size={12} aria-hidden />}
        {compact ? null : state === "playing" ? " Stop" : " Listen"}
      </button>
      {state === "playing" && line ? (
        <span className="order-last basis-full truncate text-[11px] italic text-text-muted" aria-live="polite" data-testid={`${testId}-listen-line`}>{line}</span>) : null}
      {note ? (
        <span className="order-last basis-full text-[11px] text-text-muted" role="status" data-testid={`${testId}-listen-note`}>
          {note}{note === CHOOSE_VOICE_NOTE ? <> · <a className="text-accent underline" href={VOICE_SETTINGS_HREF}>Open Settings → Voice</a></> : null}
        </span>) : null}
    </>
  );
}
