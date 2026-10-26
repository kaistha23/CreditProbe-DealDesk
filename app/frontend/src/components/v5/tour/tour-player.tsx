"use client";

/**
 * Noor's introduction tour, the player (PLAN_R14 session t; K36, K36a).
 *
 * Plays the script from `GET /api/v1/tour/script` over the live product: for each step it takes the step's action by
 * clicking (the primary navigation, the Brief/Ask tabs, the Deal Desk steps, a tools menu: N6, clicks not URLs; a
 * route push only when the link is not on the page), waits for the step's element, highlights it, shows the caption
 * and, only when the reader pressed "Play with voice" during this tour (R16 M1; captions by default), reads the voice line
 * with the voice chosen in Settings → Voice. When the line (or the step's own timer) ends it moves on. A step whose element is not on
 * this build is skipped when the script marks it optional; otherwise its caption shows without a highlight.
 *
 * Controls: play/pause, back, next, skip, captions on/off, play with voice (off by default), English/Arabic. Keyboard: → next, ← back, Esc closes.
 * State for walk-throughs is on `[data-testid="tour-player"]` (data-step, data-index, data-status, data-target).
 */
import * as React from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Captions, Pause, Play, RotateCcw, Volume2, VolumeX, X } from "lucide-react";

import { cn } from "@/lib/utils";

import { fetchTour } from "./tour-client";
import { TourDiagram } from "./tour-diagram";
import {
  clampIndex, firstPresent, LABELS, needsNavigation, sequenceTimes, stepMs, type TourLang, type TourScript, type TourStatus,
  type TourStep,
} from "./tour-model";
import { cancelSpeech, guardSpeech, speak, tourVoice } from "./tour-voice";

const WAIT_MS = 15_000;
const PREFER_MS = 7_000;
const POLL_MS = 150;

// ---------------------------------------------------------------- the page, read and clicked

const HAS_TEXT = /^(.*):has-text\("([^"]+)"\)$/;

/** querySelector with Playwright's `:has-text("…")` suffix understood (the script may carry it). */
function query(sel: string): HTMLElement | null {
  const m = HAS_TEXT.exec(sel.trim());
  try {
    if (m) {
      const [, base, text] = m;
      const scope = base.trim() ? Array.from(document.querySelectorAll<HTMLElement>(base.trim())) : [];
      return scope.find((el) => (el.textContent ?? "").includes(text) && visible(el)) ?? null;
    }
    const all = Array.from(document.querySelectorAll<HTMLElement>(sel));
    return all.find(visible) ?? null;
  } catch {
    return null;
  }
}

function visible(el: HTMLElement): boolean {
  if (el.closest("[data-tour-ui]")) return el.matches('[data-tour="tour-diagram"]');
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}

const sleep = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms));

async function waitFor(selectors: readonly string[], ms: number, alive: () => boolean): Promise<string | null> {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (!alive()) return null;
    const hit = firstPresent(selectors, (s) => !!query(s));
    if (hit) return hit;
    await sleep(POLL_MS);
  }
  return null;
}

async function clickFirst(selectors: readonly string[] | undefined, ms: number, alive: () => boolean): Promise<boolean> {
  if (!selectors?.length) return false;
  const hit = await waitFor(selectors, ms, alive);
  if (!hit || !alive()) return false;
  query(hit)?.click();
  return true;
}

function escape(): void {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
}

const path = () => window.location.pathname;

async function waitPath(pred: (p: string) => boolean, ms: number, alive: () => boolean): Promise<boolean> {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (!alive()) return false;
    if (pred(path())) return true;
    await sleep(POLL_MS);
  }
  return pred(path());
}

/** Take the step's action. Every move is a click on what a person would click; a push only as the last resort. */
async function act(step: TourStep, push: (href: string) => void, alive: () => boolean): Promise<void> {
  const a = step.action;
  const goHome = async () => {
    if (path() === "/") return;
    if (!(await clickFirst(['header a[href="/"]'], 2000, alive))) push("/");
    await waitPath((p) => p === "/", 8000, alive);
  };
  const tab = async (t: string | undefined) => {
    if (!t) return;
    const sel = `[data-testid="home-tab-${t}"]`;
    await waitFor([sel], WAIT_MS, alive);
    const el = query(sel);
    if (el && el.getAttribute("aria-selected") !== "true") el.click();
  };
  switch (a.type) {
    case "home":
    case "brief":
      await goHome();
      await tab(a.tab);
      return;
    case "ask":
      await goHome();
      await tab("ask");
      if (await waitFor(['[data-testid="cockpit-v4-question"]'], 5000, alive)) {
        query('[data-testid="cockpit-v4-question"]')?.focus({ preventScroll: true });
      }
      return;
    case "diagram":
      await goHome();
      return;
    case "open_module": {
      const href = a.href ?? step.route;
      if (!needsNavigation(path(), href)) return;
      if (!(await clickFirst(a.click, 2500, alive))) push(href);
      await waitPath((p) => p === href || p.startsWith(`${href}/`), 10_000, alive);
      return;
    }
    case "open_deal": {
      const target = step.route;
      const moved = path() !== target;
      if (moved) {
        if (path() !== "/deal-desk") {
          if (!(await clickFirst(a.click, 2500, alive))) push("/deal-desk");
          await waitPath((p) => p === "/deal-desk", 10_000, alive);
        }
        if (!(await clickFirst(a.open, 8000, alive))) push(target);
        await waitPath((p) => p === target, 15_000, alive);
      }
      // a freshly opened deal page renders its steps after the deal loads
      await clickFirst(a.then, moved ? 8000 : 1500, alive);
      return;
    }
    case "panel":
    case "click": {
      if (step.route !== "/" && needsNavigation(path(), step.route)) {
        if (!(await clickFirst(a.click?.filter((s) => s.startsWith("nav")), 2500, alive))) push(step.route);
        await waitPath((p) => p === step.route, 10_000, alive);
      }
      const own = (a.click ?? []).filter((s) => !s.startsWith("nav"));
      if (own.length) await clickFirst(own, 8000, alive);
      for (const sel of a.then ?? []) {
        if (!alive()) return;
        // `then` lists alternatives for one click (data-tour hook first) unless they are a sequence (menu → item)
        const clicked = await clickFirst([sel], a.type === "panel" ? 8000 : 1200, alive);
        if (clicked && a.type !== "panel") break;
        if (clicked) await sleep(300);
      }
      return;
    }
  }
}

// ---------------------------------------------------------------- the player

export interface TourPlayerProps {
  lang: TourLang;
  speed: number;
  onLang: (l: TourLang) => void;
  onClose: () => void;
}

export function TourPlayer({ lang, speed, onLang, onClose }: TourPlayerProps) {
  const router = useRouter();
  const L = LABELS[lang];
  const [script, setScript] = React.useState<TourScript | null>(null);
  const [index, setIndex] = React.useState(0);
  const [status, setStatus] = React.useState<TourStatus>("loading");
  const [captions, setCaptions] = React.useState(true);
  // R16 M1: the tour is silent (captions) until the reader presses "Play with voice" in this tour.
  const [voiceOn, setVoiceOn] = React.useState(false);
  const voiceRef = React.useRef(false);
  const [target, setTarget] = React.useState<string | null>(null);
  const [rect, setRect] = React.useState<DOMRect | null>(null);
  const [note, setNote] = React.useState("");
  const [skipped, setSkipped] = React.useState<string[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [showSources, setShowSources] = React.useState(false);
  const token = React.useRef(0);
  const playing = React.useRef(true);
  const indexRef = React.useRef(0);
  const prev = React.useRef<TourStep | null>(null);
  const again = React.useRef<(s: TourScript, i: number) => void>(() => {});

  // While the tour is open only its own lines are spoken (a page it opens may read aloud by itself).
  const guarded = status !== "done" && status !== "error";
  React.useEffect(() => {
    guardSpeech(guarded);
    return () => { if (guarded) { cancelSpeech(); guardSpeech(false); } };
  }, [guarded]);

  // The script, in the chosen language (the step index is kept when the language changes).
  React.useEffect(() => {
    let live = true;
    fetchTour(lang).then(
      (s) => { if (live) { setScript(s); setStatus((st) => (st === "loading" || st === "error" ? (playing.current ? "playing" : "paused") : st)); } },
      () => { if (live) setStatus("error"); },
    );
    return () => { live = false; };
  }, [lang]);

  const push = React.useCallback((href: string) => router.push(href), [router]);

  const leave = React.useCallback(() => {
    if (prev.current?.action.close_after) escape();
    prev.current = null;
  }, []);

  // Run one step: act, find the element, highlight, read, move on.
  const run = React.useCallback(async (s: TourScript, i: number) => {
    const my = ++token.current;
    const alive = () => token.current === my;
    cancelSpeech();
    leave();
    const step = s.steps[i];
    indexRef.current = i;
    setIndex(i);
    setTarget(null);
    setRect(null);
    setBusy(true);
    try {
      await act(step, push, alive);
    } catch {
      /* the caption still shows */
    }
    if (!alive()) return;
    // The step's own element first (all but its last selector, which is the fall-back such as the page's main area),
    // so a page that renders its frame before its content is highlighted on the content.
    const prefer = step.selectors.length > 1 ? step.selectors.slice(0, -1) : step.selectors;
    const hit = step.action.type === "diagram" ? '[data-tour="tour-diagram"]'
      : (await waitFor([...prefer, ...step.wait_for], PREFER_MS, alive))
        ?? (alive() ? await waitFor([...step.selectors, ...step.wait_for], WAIT_MS - PREFER_MS, alive) : null);
    if (!alive()) return;
    setBusy(false);
    prev.current = step;
    if (!hit && step.optional) {
      setSkipped((k) => (k.includes(step.key) ? k : [...k, step.key]));
      if (i < s.steps.length - 1) { again.current(s, i + 1); return; }
      setStatus("done");
      return;
    }
    setTarget(hit);
    if (hit) query(hit)?.scrollIntoView({ block: "center", behavior: "smooth" });
    if (!playing.current) return;
    // Within the step, the highlight follows what is being read (the brief's two lines).
    const ms = stepMs(step, speed);
    for (const { selector, at } of sequenceTimes(step.caption, step.action.sequence, s.lang)) {
      window.setTimeout(() => { if (alive() && query(selector)) setTarget(selector); }, Math.round(at * ms));
    }
    const voice = speed === 1 && voiceRef.current ? await tourVoice(s.lang) : null;
    if (!alive()) return;
    let outcome: string = "no-voice";
    const started = Date.now();
    if (voice) {
      setNote("");
      outcome = await speak(step.voice, s.lang);
      if (!alive()) return;
    } else {
      setNote(speed === 1 && voiceRef.current ? LABELS[s.lang].noVoice : "");
    }
    if (outcome === "blocked") setNote(LABELS[s.lang].blocked);
    if (outcome !== "ended") {
      const left = stepMs(step, speed) - (Date.now() - started);
      if (left > 0) await sleep(left);
    } else {
      await sleep(Math.round(500 / speed));
    }
    if (!alive() || !playing.current) return;
    if (i < s.steps.length - 1) again.current(s, i + 1);
    else { leave(); setStatus("done"); setTarget(null); }
  }, [push, speed, leave]);
  React.useEffect(() => { again.current = (s, i) => { void run(s, i); }; }, [run]);

  // Start (and restart on a language change, at the same step).
  React.useEffect(() => {
    if (!script) return;
    void run(script, clampIndex(indexRef.current, script.steps.length));
    const t = token;
    return () => { t.current++; cancelSpeech(); };
  }, [script, run]);

  // Follow the highlighted element as the page moves.
  React.useEffect(() => {
    if (!target) return;
    let raf = 0;
    let last = "";
    const tick = () => {
      const el = query(target);
      const r = el?.getBoundingClientRect() ?? null;
      const k = r ? `${Math.round(r.x)},${Math.round(r.y)},${Math.round(r.width)},${Math.round(r.height)}` : "";
      if (k !== last) { last = k; setRect(r); }
      raf = window.setTimeout(tick, 200);
    };
    tick();
    return () => window.clearTimeout(raf);
  }, [target]);

  const go = React.useCallback((i: number) => {
    if (!script) return;
    playing.current = status !== "paused";
    setStatus(playing.current ? "playing" : "paused");
    void run(script, clampIndex(i, script.steps.length));
  }, [script, run, status]);

  const toggle = React.useCallback(() => {
    if (!script) return;
    if (status === "done") { playing.current = true; setStatus("playing"); setSkipped([]); void run(script, 0); return; }
    if (status === "playing") {
      playing.current = false;
      token.current++;
      cancelSpeech();
      setBusy(false);
      setStatus("paused");
    } else {
      playing.current = true;
      setStatus("playing");
      void run(script, indexRef.current);
    }
  }, [script, status, run]);

  // The reader's click turns the voice on (the gesture the browser needs) and reads the current step now; off stops it.
  const toggleVoice = React.useCallback(() => {
    const next = !voiceRef.current;
    voiceRef.current = next;
    setVoiceOn(next);
    if (!next) { cancelSpeech(); setNote(""); return; }
    // Read the step on screen now (later steps read their own lines); the step's own timer still moves the tour on.
    const step = script?.steps[indexRef.current];
    if (step && speed === 1) {
      void tourVoice(lang).then((v) => {
        if (!v) { setNote(LABELS[lang].noVoice); return; }
        if (voiceRef.current) void speak(step.voice, lang);
      });
    }
  }, [script, speed, lang]);

  const close = React.useCallback(() => {
    token.current++;
    cancelSpeech();
    leave();
    onClose();
  }, [onClose, leave]);

  React.useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (!e.isTrusted) return;   // the tour's own Escape (closing a drawer) is not the reader's
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.key === "ArrowRight") { e.preventDefault(); go(indexRef.current + 1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(indexRef.current - 1); }
      else if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [go, close]);

  const step = script?.steps[index] ?? null;
  const n = script?.steps.length ?? 0;
  const dir = lang === "ar" ? "rtl" : "ltr";
  const pad = 6;
  const hole = rect && step?.action.type !== "diagram"
    ? { left: rect.left - pad, top: rect.top - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 } : null;
  const big = !!hole && hole.width * hole.height > window.innerWidth * window.innerHeight * 0.45;
  const cardTop = !!hole && !big && hole.top + hole.height > window.innerHeight - 260;

  return (
    <div data-tour-ui="" data-testid="tour-player" data-step={step?.key ?? ""} data-index={index} data-status={status}
         data-lang={lang} data-target={target ?? ""} data-busy={busy ? "true" : "false"} data-skipped={skipped.join(",")}
         data-n={n}>
      {/* The dim with a hole around the element Noor is talking about (clicks pass through). */}
      {status !== "done" && status !== "error" ? (
        hole && !big ? (
          <div aria-hidden className="pointer-events-none fixed z-[80] rounded-lg ring-2 ring-accent transition-all duration-300"
               style={{ ...hole, boxShadow: "0 0 0 9999px rgba(15, 23, 42, 0.42)" }} data-testid="tour-spotlight" />
        ) : (
          <div aria-hidden className={cn("pointer-events-none fixed inset-0 z-[80] transition-colors",
                                         big ? "bg-slate-900/10" : "bg-slate-900/40")} />
        )
      ) : null}

      {step?.action.type === "diagram" && status !== "done" ? (
        <div className="pointer-events-none fixed inset-0 z-[85] flex items-center justify-center pb-40">
          <div className="pointer-events-auto"><TourDiagram lang={lang} /></div>
        </div>
      ) : null}

      <section role="dialog" aria-modal="false" aria-label={L.take} dir={dir} data-testid="tour-card"
               className={cn("fixed left-1/2 z-[90] w-[min(600px,calc(100vw-2rem))] -translate-x-1/2 rounded-xl border",
                             "border-border bg-surface shadow-2xl", cardTop ? "top-16" : "bottom-6")}>
        <div className="h-1 overflow-hidden rounded-t-xl bg-surface-sunken">
          <div className="h-full bg-accent transition-all duration-500" data-testid="tour-progress"
               style={{ width: n ? `${((status === "done" ? n : index + 1) / n) * 100}%` : "0%" }} />
        </div>
        <div className="px-5 pb-4 pt-3">
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted" data-testid="tour-eyebrow">
              {status === "done" ? L.done : step ? `${L.step} ${index + 1} ${L.of} ${n} · ${step.title}` : L.loading}
            </p>
            <button type="button" onClick={close} aria-label={L.close} title={L.close} data-testid="tour-close"
                    className="rounded-md p-1 text-text-muted hover:bg-surface-hover hover:text-text-primary">
              <X size={15} aria-hidden />
            </button>
          </div>
          {status === "error" ? (
            <p className="mt-2 text-[14px] text-text-secondary" data-testid="tour-error">{L.error}</p>
          ) : status === "done" ? (
            <p className="mt-2 text-[15px] leading-relaxed text-text-primary" data-testid="tour-caption">
              {script?.steps[n - 1]?.caption}
            </p>
          ) : captions && step ? (
            <p className="mt-2 min-h-[3em] text-[15px] leading-relaxed text-text-primary" data-testid="tour-caption"
               lang={lang}>{step.caption}</p>
          ) : (
            <p className="mt-2 min-h-[1.5em] text-[13px] text-text-muted">{step?.title ?? L.loading}</p>
          )}
          {note ? <p className="mt-1.5 text-[12px] text-text-muted" data-testid="tour-note">{note}</p> : null}
          {step && script && status !== "done" && sourcesOf(step, script).length ? (
            <details className="mt-1.5 text-[11.5px] text-text-muted" data-testid="tour-sources"
                     open={showSources} onToggle={(e) => setShowSources((e.target as HTMLDetailsElement).open)}>
              <summary className="cursor-pointer select-none hover:text-text-secondary">
                {L.sources} ({sourcesOf(step, script).length})
              </summary>
              <ul className="mt-1 space-y-0.5" dir="ltr">
                {sourcesOf(step, script).map((f) => (
                  <li key={f.id} className="truncate" title={f.method}>
                    <span className="font-mono text-[11px]">{f.domain}.{f.relation}</span>
                    {f.period ? ` · ${f.period}` : ""} · {f.method}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          <div className="mt-3 flex items-center justify-between gap-2" dir="ltr">
            <div className="flex items-center gap-1.5">
              <Ctl onClick={() => go(index - 1)} disabled={!script || index === 0 || status === "done"} label={L.back}
                   testId="tour-back"><ChevronLeft size={15} aria-hidden /></Ctl>
              <button type="button" onClick={toggle} disabled={!script} data-testid="tour-play"
                      data-state={status === "playing" ? "playing" : "paused"}
                      className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-3.5 text-[13px] font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-50">
                {status === "done" ? <><RotateCcw size={14} aria-hidden />{L.restart}</>
                  : status === "playing" ? <><Pause size={14} aria-hidden />{L.pause}</>
                  : <><Play size={14} aria-hidden />{L.play}</>}
              </button>
              <Ctl onClick={() => go(index + 1)} disabled={!script || index >= n - 1 || status === "done"} label={L.next}
                   testId="tour-next"><ChevronRight size={15} aria-hidden /></Ctl>
            </div>
            <div className="flex items-center gap-1.5">
              <Ctl onClick={() => setCaptions((c) => !c)} label={L.captions} testId="tour-captions"
                   pressed={captions}><Captions size={15} aria-hidden /></Ctl>
              <Ctl onClick={toggleVoice} label={voiceOn ? L.voiceOff : L.voiceOn} testId="tour-voice"
                   pressed={voiceOn}>{voiceOn ? <Volume2 size={15} aria-hidden /> : <VolumeX size={15} aria-hidden />}</Ctl>
              <button type="button" onClick={() => onLang(lang === "ar" ? "en" : "ar")} data-testid="tour-lang"
                      className="h-8 rounded-md border border-border px-2.5 text-[12.5px] text-text-secondary hover:bg-surface-hover">
                {L.lang}
              </button>
              <button type="button" onClick={close} data-testid="tour-skip"
                      className="h-8 rounded-md px-2.5 text-[12.5px] text-text-muted hover:bg-surface-hover hover:text-text-primary">
                {status === "done" ? L.close : L.skip}
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

/** The facts behind the step's figures, each with its relation and method (N3: every number traces to the data). */
function sourcesOf(step: TourStep, script: TourScript) {
  const seen = new Set<string>();
  return step.facts.map((k) => script.facts[k]).filter((f) => {
    if (!f) return false;
    const key = `${f.domain}.${f.relation}.${f.method}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function Ctl({ children, onClick, disabled, label, testId, pressed }: {
  children: React.ReactNode; onClick: () => void; disabled?: boolean; label: string; testId: string; pressed?: boolean;
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={label} title={label} data-testid={testId}
            aria-pressed={pressed}
            className={cn("inline-flex size-8 items-center justify-center rounded-md border border-border text-text-secondary",
                          "hover:bg-surface-hover hover:text-text-primary disabled:opacity-40",
                          pressed ? "bg-accent-muted text-accent" : "")}>
      {children}
    </button>
  );
}
