"use client";

/**
 * Noor's threads, shared by the top-bar panel, the module briefs and the Cockpit brief panel.
 *
 * A module-level store (not a React context) because the panel lives in the app header while the module briefs live
 * in the pages: the two are siblings in the app shell. R14 n (K5, K7, K16) replaces the one long thread:
 *
 *   opening the panel (Ask Noor, any module) starts an EMPTY thread scoped to the page;
 *   a brief line's Why / What to do / Open starts or resumes THAT LINE's thread (keyed `line:<id>`), scrolled to its top;
 *   a question typed in the panel continues the open thread; earlier threads go to the panel's history list.
 *
 * Threads are kept for the browser session (sessionStorage, per user). Answers land in the thread that asked, even
 * when the reader has switched threads meanwhile.
 */

import * as React from "react";

import { recallDomain } from "@/components/cockpit-v4/domain-switch";

import { noor } from "./noor-client";
import { dispatch } from "./noor-dispatch";
import {
  type Brief, type BriefItem, type DecisionOption, type NoorSettings, type NoorThread, type Persona, type Turn,
  addThreadTurn, findThread, lineKey, newThread, putThread, restoreThreads, restoreTurns, speakable, spokenOpening,
  turnId,
} from "./noor-model";
import { ENGINE_LABEL, ENGINE_VERB, routeQuestion } from "./noor-route";
import { intelHref, routeIntel } from "@/lib/v5/intel-intents";
import { herePath, withFrom } from "@/components/v5/ui/back-link-model"; // R14 U (K1)
import { isNeural, normaliseChosen, readChosen, resolveChosen, writeChosen } from "./voice-choice";
import { type PageContext, readPageContext, routeHere } from "./noor-context";
import type { HereAnswer, PageContextLike } from "./noor-model";
import {
  type VoiceLanguage, type VoicePref, type VoiceState, effectiveVoice, knownVoices, loadVoices, pickVoice,
  readPref, speakText, speechSupported, CHOOSE_VOICE_NOTE, stopSpeech, voiceStateFor, voicesLoaded, writePref,
} from "./noor-voice";

/** The reader's voice (J1): on or off and the language are the reader's own choice, kept per user. */
export interface NoorVoice { on: boolean; language: VoiceLanguage; state: VoiceState; voiceName: string; chosen: boolean;
  /** R16 M1: set when a speaker click found no voice chosen for the language ("Choose a voice in Settings → Voice"). */
  notice?: string;
  /** R15 L2: the voice reading is the one chosen in Settings -> Voice (false: the interim pick, "not chosen yet"). */
  fixed?: boolean }

export interface NoorState {
  open: boolean;
  /** The open thread's turns (what the panel shows). */
  turns: Turn[];
  threads: NoorThread[];
  current: string | null;
  historyOpen: boolean;
  /** Bumped when the open thread changes, so the panel scrolls to the thread's top. */
  switched: number;
  busy: boolean;
  brief: Brief | null;
  settings: NoorSettings;
  persona: Persona;
  module: { id: string; label: string };
  user: string;
  settingsOpen: boolean;
  voice: NoorVoice;
}

const DEFAULT_SETTINGS: NoorSettings = { name: "Noor", speak_first: true,
                                         voice: { enabled: false, gender: "male", language: "en" } };  // R16 M1: voice off by default

let state: NoorState = {
  open: false, turns: [], threads: [], current: null, historyOpen: false, switched: 0, busy: false, brief: null, settings: DEFAULT_SETTINGS, persona: "analyst",
  module: { id: "cockpit", label: "the Cockpit" }, user: "", settingsOpen: false,
  voice: { on: false, language: "en", state: "loading", voiceName: "", chosen: false },
};
let pref: VoicePref = { on: null, language: null };
const listeners = new Set<() => void>();
let navigate: (href: string) => void = (href) => { window.location.assign(href); };
/** R14 U (K1): every navigation from Noor carries its origin (Brief on the home page, else the Noor panel) and the
 *  exact screen to return to, so the target page shows "← Back to Brief" and the browser's Back works too. */
function via(href: string, kind: "brief" | "ask"): string {
  if (typeof window === "undefined") return href;
  const home = window.location.pathname === "/";
  return withFrom(href, home ? kind : "noor", herePath(window.location));
}
let attentionReader: (() => Promise<unknown[]>) | null = null;

function emit() { listeners.forEach((fn) => fn()); }

function set(patch: Partial<NoorState>) {
  state = { ...state, ...patch };
  if ((patch.threads || patch.current !== undefined) && state.user) {
    try {
      window.sessionStorage.setItem(`noor.threads.${state.user}`, JSON.stringify({ threads: state.threads, current: state.current }));
    } catch { /* ignore */ }
  }
  emit();
}

function currentThread(): NoorThread | null {
  return state.threads.find((t) => t.id === state.current) ?? null;
}

/** Make `th` the open thread (scrolled to its top). */
function show(th: NoorThread, patch: Partial<NoorState> = {}) {
  const threads = putThread(state.threads, th);
  set({ ...patch, threads, current: th.id, turns: th.turns, switched: state.switched + 1, historyOpen: false });
}

/** A new empty thread scoped to the page, unless the open one is still empty (then it is reused). */
export function newNoorThread(key: string | null = null, title = "New thread"): string {
  const cur = currentThread();
  if (cur && !cur.turns.length && !cur.key) {
    const th = { ...cur, key, title, module: state.module.id };
    show(th);
    return th.id;
  }
  const th = newThread(state.module.id, key, title);
  show(th);
  return th.id;
}

/** Open (or resume) the thread of one key, e.g. a brief line; returns its id. */
function threadOf(key: string, title: string): string {
  const got = findThread(state.threads, key);
  if (got) { show(got); return got.id; }
  return newNoorThread(key, title);
}

export function selectThread(id: string) {
  const th = state.threads.find((t) => t.id === id);
  if (th) show(th, { open: true });
}

export function toggleHistory() { set({ historyOpen: !state.historyOpen }); }

export function useNoor(): NoorState {
  return React.useSyncExternalStore(
    (fn) => { listeners.add(fn); return () => listeners.delete(fn); },
    () => state, () => state);
}

// ---------------------------------------------------------------- wiring (called by NoorTopBar)

export const noorWiring = {
  setNavigate(fn: (href: string) => void) { navigate = fn; },
  setAttentionReader(fn: (() => Promise<unknown[]>) | null) { attentionReader = fn; },
  setUser(user: string) {
    if (user === state.user) return;
    let saved: { threads: NoorThread[]; current: string | null } = { threads: [], current: null };
    try { saved = restoreThreads(window.sessionStorage.getItem(`noor.threads.${user}`)); } catch { /* ignore */ }
    // The R13 single thread, if any, becomes one history entry (nothing is lost; it is never appended to again).
    try {
      const old = restoreTurns(window.sessionStorage.getItem(`noor.thread.${user}`));
      if (old.length && !saved.threads.length) {
        const th = { ...newThread("cockpit", null, "Earlier conversation"), turns: old };
        saved = { threads: [th], current: null };
      }
    } catch { /* ignore */ }
    const briefs = saved.threads.flatMap((t) => t.turns).filter((t) => t.kind === "brief");
    const lastBrief = briefs[briefs.length - 1];
    const cur = saved.threads.find((t) => t.id === saved.current) ?? null;
    set({ user, threads: saved.threads, current: cur?.id ?? null, turns: cur?.turns ?? [],
          brief: lastBrief && lastBrief.kind === "brief" ? lastBrief.brief : null });
    pref = readPref(user);
    applyVoice();
    // The service keeps the choice per user, so it follows the reader to another browser.
    noor.voice().then((v) => {
      if (pref.on === null && v.on !== null) pref = { ...pref, on: v.on };
      if (pref.language === null && v.language) pref = { ...pref, language: v.language };
      writePref(user, pref);
      applyVoice();
    }, () => undefined);
  },
  setPersona(p: Persona) {
    if (p === state.persona) return;
    const hadBrief = Boolean(state.brief);
    set({ persona: p });
    if (hadBrief && state.open) void loadBrief();
  },
  setModule(m: { id: string; label: string }) {
    if (m.id !== state.module.id) set({ module: m });
  },
  setSettings(s: NoorSettings) { set({ settings: s }); writeChosen(normaliseChosen(s.voice?.chosen)); applyVoice(); },
};

// ---------------------------------------------------------------- actions

/** Add a turn to thread `tid` (default: the open one). Answers land in the thread that asked. */
function push(turn: Turn, replacing?: string, tid: string | null = state.current) {
  let th = state.threads.find((t) => t.id === tid) ?? null;
  if (!th) th = newThread(state.module.id);
  const next = addThreadTurn(th, turn, replacing);
  const threads = putThread(state.threads, next);
  set(next.id === state.current || !state.current
    ? { threads, current: next.id, turns: next.turns } : { threads });
}

function pending(text: string, tid: string | null = state.current): string {
  const id = turnId("p");
  push({ id, kind: "pending", text }, undefined, tid);
  return id;
}

function fail(id: string, e: unknown, tid: string | null = state.current) {
  push({ id: turnId("e"), kind: "error", text: e instanceof Error ? e.message : "Noor could not answer that." }, id, tid);
}

/** A brief read by the page (the Home Brief tab) becomes the panel's brief, so typed questions match its lines. */
export function adoptBrief(brief: Brief) {
  if (!state.brief || state.brief.persona !== brief.persona || state.brief.date !== brief.date) set({ brief });
}

/** K7: opening the panel starts an empty thread scoped to the page (earlier threads stay in the history list). */
export function openPanel(open = true) {
  if (open && !state.open) { set({ open: true }); newNoorThread(); return; }
  set({ open });
}
export function togglePanel() { openPanel(!state.open); }
export function toggleSettings() { set({ settingsOpen: !state.settingsOpen }); }
/** "New thread": an empty thread; the open one goes to the history list. */
export function clearThread() { newNoorThread(); }

export async function loadBrief(opts: { module?: string; quiet?: boolean; open?: boolean } = {}): Promise<Brief | null> {
  set({ open: opts.open ?? true, busy: true });
  // One brief thread per persona and module: reading the brief again refreshes it (no duplicate entries in history).
  const key = `brief:${state.persona}:${opts.module ?? ""}`;
  const title = opts.module ? `What matters in ${state.module.label}` : "Today's brief";
  const had = findThread(state.threads, key);
  let tid: string;
  if (had) {
    show({ ...had, turns: [], updated: Date.now() }, { open: opts.open ?? true });
    tid = had.id;
  } else {
    tid = newNoorThread(key, title);
  }
  const p = pending(opts.module ? "Reading this screen's sources" : "Reading every source for your brief", tid);
  try {
    let attention: unknown[] = [];
    if (!opts.module && attentionReader) {
      // The Cockpit cards are evidence, not a gate: the brief never waits more than 2.5 s for them.
      const reader = attentionReader;
      try {
        attention = await Promise.race([reader(), new Promise<unknown[]>((ok) => setTimeout(() => ok([]), 2500))]);
      } catch { attention = []; }
    }
    const brief = await noor.brief({ persona: state.persona, module: opts.module, attention });
    push({ id: turnId("b"), kind: "brief", brief, module: state.module.id }, p, tid);
    set({ brief: opts.module ? state.brief ?? brief : brief, busy: false });
    // R16 M1: a brief that loads is shown, never spoken; speech starts only from a speaker click.
    return brief;
  } catch (e) {
    fail(p, e, tid);
    set({ busy: false });
    return null;
  }
}

/** The line in a few words, for the question bubble: the sector, deal queue or name, else the line's start. */
function subject(item: BriefItem): string {
  const name = String(item.entity?.name ?? "");
  if (name) return name;
  const t = item.title.split(/[:;(]|,\s/)[0].trim();
  return t.length > 70 ? `${t.slice(0, 68)}…` : t;
}

/**
 * K5: a brief line's actions run in that line's own thread (started, or resumed when it exists). `here` keeps a
 * follow-up typed inside the open thread in that thread (K5: "follow-up questions stay in the current thread").
 */
function lineThread(item: BriefItem, here: boolean): string {
  if (here && state.current) return state.current;
  return threadOf(lineKey(item), subject(item));
}

export async function askWhy(item: BriefItem, opts: { here?: boolean } = {}) {
  set({ open: true, busy: true });
  const tid = lineThread(item, Boolean(opts.here));
  push({ id: turnId("q"), kind: "ask", text: `Why? ${subject(item)}`, module: state.module.id }, undefined, tid);
  const p = pending("Working it out", tid);
  try {
    const answer = await noor.why(item);
    push({ id: turnId("w"), kind: "why", item, answer }, p, tid);
  } catch (e) { fail(p, e, tid); }
  set({ busy: false });
}

export async function askOptions(item: BriefItem, opts: { here?: boolean } = {}) {
  set({ open: true, busy: true });
  const tid = lineThread(item, Boolean(opts.here));
  push({ id: turnId("q"), kind: "ask", text: `What should we do? ${subject(item)}`, module: state.module.id }, undefined, tid);
  const p = pending("Pricing the options with the engines", tid);
  try {
    const answer = await noor.options(item);
    push({ id: turnId("o"), kind: "options", item, answer }, p, tid);
  } catch (e) { fail(p, e, tid); }
  set({ busy: false });
}

/** Who drives it? The named borrowers behind a line (I12 point-and-ask). */
export async function askDrivers(item: BriefItem, opts: { here?: boolean } = {}) {
  set({ open: true, busy: true });
  const tid = lineThread(item, opts.here ?? true);
  push({ id: turnId("q"), kind: "ask", text: `Who drives it? ${subject(item)}`, module: state.module.id }, undefined, tid);
  const p = pending("Finding the names behind it", tid);
  try {
    const answer = await noor.drivers(item);
    push({ id: turnId("d"), kind: "drivers", item, answer }, p, tid);
  } catch (e) { fail(p, e, tid); }
  set({ busy: false });
}

/** Go somewhere with the panel open (a name in a table, a Show me link). */
export function go(href: string) {
  set({ open: true });
  navigate(via(href, "brief"));
}

export async function sendToCommittee(item: BriefItem, option: DecisionOption) {
  set({ busy: true });
  const tid = state.current;
  push({ id: turnId("q"), kind: "ask", text: `Send to committee: ${option.title}`, module: state.module.id }, undefined, tid);
  const p = pending("Creating the committee item", tid);
  try {
    const result = await noor.committee(item, option);
    push({ id: turnId("c"), kind: "committee", item, option, result }, p, tid);
  } catch (e) { fail(p, e, tid); }
  set({ busy: false });
}

/** Show me: go to the module, already filtered; the panel stays open (I13.3), on the line's thread. */
export function showMe(item: BriefItem, opts: { here?: boolean } = {}) {
  set({ open: true });
  const tid = lineThread(item, opts.here ?? true);
  push({ id: turnId("n"), kind: "note", text: `${item.show_me.label.replace(/^Show /, "Showing ")}.`, module: state.module.id }, undefined, tid);
  navigate(via(item.show_me.href, "brief"));  // R14 x: u's via() (K1) in n's line thread (K5)
}

/** Open: the item itself. K5: the line's thread records it, so the line's history is in one place. */
export function openItem(item: BriefItem) {
  if (state.open) {
    const tid = lineThread(item, false);
    push({ id: turnId("n"), kind: "note", text: `Opened: ${item.open.label}.`, module: state.module.id }, undefined, tid);
  }
  navigate(via(item.open.href, "brief"));  // R14 x: u's via() (K1) in n's line thread (K5)
}

/**
 * Typed text (R13 H, J2 (b)): answered, never refused. A question about a line of today's brief is answered on that
 * line (Why? / What should we do? / Who drives it? / Show me); "today's brief" reloads it; anything else goes to the
 * engine that answers it (the Cockpit by default, What-If, Lenses or Deal Desk), with the panel kept open.
 */
export async function ask(text: string) {
  const t = text.trim();
  if (!t) return;
  // Typed inside the panel: it continues the open thread (an empty one takes this question as its title).
  if (!state.current) newNoorThread();
  const tid = state.current;
  // R15 L9: the page first. On a deal page a stress question is answered on the run on screen; "this", "it", "here"
  // are the object on screen; only a question about the book (or another module's job) leaves the page.
  const ctx = readPageContext();
  const h = routeHere(t, ctx);
  if (h.here && ctx && h.topic === "stress") return askHere(t, ctx);
  const away = !h.here && h.reason && ctx?.deal_id ? { why: h.reason, here: ctx } : null;
  const items = state.brief ? [...state.brief.items, ...state.brief.more] : [];
  const r = routeQuestion(t, items);
  if (r.engine === "none") return;
  // R13 M (§I): a job one of the CCO intelligence engines finishes opens that engine's panel (over the page it lives on),
  // unless the question is plainly about a line of today's brief ("who should I call today?" is not "today's brief").
  if (!(r.engine === "brief" && r.item)) {
    const path = typeof window !== "undefined" ? window.location.pathname : "";
    const deal = /^\/deal-desk\/([^/?#]+)$/.exec(path)?.[1];
    const hit = routeIntel(t, { dealId: deal ? decodeURIComponent(deal) : null });
    if (hit) {
      set({ open: true });
      push({ id: turnId("q"), kind: "ask", text: t, module: state.module.id }, undefined, tid);
      const href = intelHref(hit);
      const target = hit.deal && !href.includes(hit.deal) ? `${href}${href.includes("?") ? "&" : "?"}deal=${encodeURIComponent(hit.deal)}` : href;
      // R15 L9: leaving a deal page says why, and keeps "Answer here instead".
      if (away) push({ id: turnId("r"), kind: "routed", engine: "intel", label: hit.route.label, question: t, href: target,
                       module: state.module.id, why: away.why, here: away.here }, undefined, tid);
      else push({ id: turnId("n"), kind: "note", text: `${hit.route.label}: opening it (${hit.route.home}).`, module: state.module.id }, undefined, tid);
      navigate(via(target, "ask"));
      return;
    }
  }
  // R15 L9: any other question on a deal page is about that deal (its numbers, on the step on screen).
  if (h.here && ctx) return askHere(t, ctx);
  if (r.engine === "brief") {
    if (!r.item) {
      push({ id: turnId("q"), kind: "ask", text: t, module: state.module.id }, undefined, tid);
      await loadBrief();
      return;
    }
    if (r.intent === "options") return askOptions(r.item, { here: true });
    if (r.intent === "drivers") return askDrivers(r.item, { here: true });
    if (r.intent === "show") return showMe(r.item, { here: true });
    return askWhy(r.item, { here: true });
  }
  return routeTo(r.engine, t, tid, away);
}

/** Send a question to an engine (it opens its own new thread, K16); this thread keeps the link and, when the question
 *  left a deal page, why it did and the page to "Answer here instead" (R15 L9). */
async function routeTo(engine: Exclude<ReturnType<typeof routeQuestion>["engine"], "brief" | "none">, t: string,
                       tid: string | null, away: { why: string; here: PageContext } | null, echo = true) {
  set({ open: true, busy: true });
  if (echo) push({ id: turnId("q"), kind: "ask", text: t, module: state.module.id }, undefined, tid);
  const p = pending(ENGINE_VERB[engine], tid);
  try {
    const out = await dispatch(engine, t, { domain: recallDomain() ?? "corporate" });
    push({ id: turnId("r"), kind: "routed", engine, label: ENGINE_LABEL[engine], question: t, href: out.href,
           module: state.module.id, ...(away ? { why: away.why, here: away.here } : {}) }, p, tid);
    set({ busy: false });
    navigate(via(out.href, "ask"));
  } catch (e) {
    const why = e instanceof Error && e.message && !/^request failed/i.test(e.message) ? ` ${e.message}` : "";
    push({ id: turnId("e"), kind: "error",
           text: `${ENGINE_LABEL[engine].replace(/^the /, "The ")} could not start that answer just now.${why} Please try again in a moment.` }, p, tid);
    set({ busy: false });
  }
}

const ctxHref = (c: PageContextLike) => `${c.path}${c.step ? `?step=${encodeURIComponent(c.step)}` : ""}`;

/**
 * R15 L9: answer on the page: the deal on screen, or the stress run on screen (which structures, the first scenario to
 * break at each severity, the driver chain, then the cheapest fix from Stress-proof, read a moment later). `force`
 * is the "Answer here instead" button on a question that had gone to the book.
 */
export async function askHere(t: string, ctx: PageContextLike, opts: { force?: boolean; echo?: boolean } = {}) {
  if (!state.current) newNoorThread();
  const tid = state.current;
  set({ open: true, busy: true });
  if (opts.echo !== false) push({ id: turnId("q"), kind: "ask", text: t, module: state.module.id }, undefined, tid);
  if (typeof window !== "undefined" && window.location.pathname !== ctx.path) navigate(via(ctxHref(ctx), "ask"));
  const stressy = ctx.step === "stress" || ctx.stress_on_screen;
  const p = pending(stressy ? `Reading ${ctx.deal_id}'s stress run on screen` : `Reading ${ctx.deal_id} on screen`, tid);
  try {
    const a = await noor.here(t, ctx, Boolean(opts.force));
    if (!a.here) {
      push({ id: turnId("n"), kind: "note", text: a.reason ?? "Not about the page on screen.", module: state.module.id }, p, tid);
      set({ busy: false });
      return;
    }
    const ans = a as HereAnswer;
    const id = turnId("h");
    push({ id, kind: "here", question: t, answer: ans, fix: null, module: state.module.id }, p, tid);
    set({ busy: false });
    if (ans.fix_from) {
      try {
        const fix = await noor.hereFix(ans.deal_id, ans.fix_from, ans.fix_target ?? "moderate");
        push({ id, kind: "here", question: t, answer: ans, fix, module: state.module.id }, id, tid);
      } catch {
        /* the answer stands; Stress-proof on the page still finds the fix */
      }
    }
  } catch (e) {
    fail(p, e, tid);
    set({ busy: false });
  }
}

/** The actions under a page answer: open Stress-proof on the page, or take the question to the book / the desk. */
export function hereAction(kind: "scroll" | "book" | "dealdesk", question: string, a: { target?: string; href?: string } = {}) {
  if (kind === "scroll") {
    const el = a.target && typeof document !== "undefined" ? document.querySelector<HTMLElement>(a.target) : null;
    if (el) { el.scrollIntoView({ block: "start", behavior: "smooth" }); return; }
    if (a.href) navigate(via(a.href, "ask"));
    return;
  }
  void routeTo(kind === "book" ? "whatif" : "dealdesk", question, state.current, null, false);
}

// ---------------------------------------------------------------- voice (I13.1, R13 H J1, R16 M1)
//
// R16 M1: Noor never speaks on its own. `say` (the only path to speech) is private and reached only from the click
// handlers below: `speakerButton`, `speakNow`, `listenBrief`, `speakLine`, `speakOnClick`. With no voice chosen in
// Settings → Voice for the language a click stays silent and sets `voice.notice`.

let notice = "";
let noticeTimer: ReturnType<typeof setTimeout> | null = null;

function applyVoice(patch: Partial<NoorVoice> = {}) {
  const bank = state.settings.voice;
  const eff = effectiveVoice(pref, { enabled: bank.enabled, language: bank.language });
  const voices = knownVoices();
  const { voice, fallback, notChosen, chosen: fixed } = pickVoice(voices, eff.language, "male", choiceFor(eff.language));
  // R16 v: a chosen neural voice (the offline add-on) is ready whatever the browser's own voices are.
  const st = isNeural(choiceFor(eff.language)) ? "ready"
    : voiceStateFor(speechSupported(), voicesLoaded(), voices.length, fallback, false, Boolean(notChosen));
  // A reported state ("speaking", "no-voice") wins; "ready" settles back to what the voices allow (ready or fallback).
  const reported = patch.state && patch.state !== "ready" ? patch.state : undefined;
  set({ voice: { on: eff.on, language: eff.language, voiceName: voice?.name ?? (choiceFor(eff.language)?.label || (isNeural(choiceFor(eff.language)) ? choiceFor(eff.language)?.name : "") || ""), chosen: pref.on !== null, fixed: Boolean(fixed),
                 ...(notice ? { notice } : {}),
                 state: reported ?? (state.voice.state === "speaking" && patch.state === undefined ? "speaking" : st) } });
}

/** R15 L2: the bank's chosen voice for a language (Settings -> Voice), or null while not chosen. */
function choiceFor(lang: VoiceLanguage) {
  return normaliseChosen(state.settings.voice?.chosen)[lang];
}

/** R16 n: the chosen voice for a language (the bank setting, else the one kept in this browser), for Listen on answers. */
export function chosenVoiceFor(lang: VoiceLanguage) {
  return choiceFor(lang) ?? readChosen()[lang];
}

/** Read the installed voices once the page is up (Chrome fills the list late, on `voiceschanged`). */
export function prepareVoice() {
  if (!speechSupported()) { applyVoice(); return; }
  void loadVoices().then(() => applyVoice());
}

function keep(next: VoicePref) {
  pref = next;
  writePref(state.user, pref);
  void noor.saveVoice({ ...(next.on !== null ? { on: next.on } : {}), ...(next.language ? { language: next.language } : {}) })
    .catch(() => undefined);
}

/** R16 M1: the short note after a click with no chosen voice; it clears itself after a few seconds. */
function showNotice(text: string) {
  notice = text;
  if (noticeTimer) clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { notice = ""; noticeTimer = null; applyVoice(); }, 8000);
  applyVoice();
}

export function dismissVoiceNotice() {
  notice = "";
  if (noticeTimer) { clearTimeout(noticeTimer); noticeTimer = null; }
  applyVoice();
}

/**
 * Speak, from a click only (private: every caller below is a click handler). Never throws. With no voice chosen for
 * the language nothing is spoken and the note "Choose a voice in Settings → Voice" shows; no other voice is used.
 */
function say(text: string, langOverride?: VoiceLanguage) {
  if (!text) return;
  const lang = langOverride ?? state.voice.language;
  if (!isNeural(choiceFor(lang)) && !resolveChosen(knownVoices(), choiceFor(lang)) && voicesLoaded() && knownVoices().length) {
    showNotice(CHOOSE_VOICE_NOTE);
    return;
  }
  void speakText(speakable(text), lang, "male", {
    start: () => applyVoice({ state: "speaking" }),
    end: () => applyVoice({ state: "ready" }),
  }, choiceFor(lang)).then((r) => {
    if (r.state === "not-chosen") showNotice(CHOOSE_VOICE_NOTE);
    else if (r.note) showNotice(r.note);   // R16 v: the neural add-on is absent; the browser's voice read instead
    if (r.state !== "speaking") applyVoice(r.state === "fallback" ? {} : { state: r.state });
  });
}

/** A speaker click on any other block (the "In plain words" speaker): reads `text` now, or stops when reading. */
export function speakOnClick(text: string) {
  if (state.voice.state === "speaking") { stopSpeaking(); return; }
  if (pref.on !== true) keep({ ...pref, on: true });
  applyVoice();
  say(text);
}

/**
 * The speaker button (a user gesture, so Chrome allows speech): stops if reading; otherwise turns voice on (kept for
 * this reader) and reads the brief's opening now, in the reader's language.
 */
export function speakerButton(brief?: Brief | null) {
  if (state.voice.state === "speaking") { stopSpeaking(); return; }
  // The click is the reader's choice: keep it (the icon shows voice on). Nothing is ever spoken without a click.
  if (pref.on !== true) keep({ ...pref, on: true });
  applyVoice();
  const b = brief ?? state.brief;
  const text = b ? spokenOpening(b, state.voice.language) : `I am ${state.settings.name}. Ask me anything.`;
  say(text);
}

/**
 * K10: a speaker button on a line, an answer or the brief's Listen (a click, so the browser allows speech). Reads the
 * spoken script, never the screen: the Arabic script when the reader's voice is Arabic and one exists. A second click
 * while reading stops.
 */
export function speakNow(en: string, ar?: string | null) {
  if (state.voice.state === "speaking") { stopSpeaking(); return; }
  if (pref.on !== true) keep({ ...pref, on: true });
  applyVoice();
  // An Arabic reader hears the Arabic script when there is one; English text is never read by the Arabic voice.
  if (state.voice.language === "ar-gulf" && ar) say(ar, "ar-gulf");
  else say(en, "en");
}

/** Listen to the whole brief: the headline, then one sentence per line (the brief-level script). */
export function listenBrief(brief: Brief) {
  const sc = brief.script;
  speakNow(sc?.en || spokenOpening(brief, "en"), sc?.ar || brief.opening_ar || null);
}

const scripts = new Map<string, { en: string; ar: string }>();

/** The speaker beside a brief line: that line's 40–70 second script (what, bank vs requirement, reasons, action). */
export async function speakLine(item: BriefItem) {
  if (state.voice.state === "speaking") { stopSpeaking(); return; }
  let sc = scripts.get(item.id);
  if (!sc) {
    try {
      const got = await noor.script(item);
      sc = { en: got.en, ar: got.ar };
      scripts.set(item.id, sc);
    } catch {
      sc = { en: item.title, ar: "" };
    }
  }
  speakNow(sc.en, sc.ar);
}

export function setVoiceOn(on: boolean) {
  keep({ ...pref, on });
  if (!on) stopSpeaking();
  applyVoice();
}

export function setVoiceLanguage(language: VoiceLanguage) {
  keep({ ...pref, language });
  applyVoice();
}

// R16 M1: there is no automatic speech. The old `autoSpeak` (brief load, sign-in) is deleted on purpose.

export function stopSpeaking() {
  stopSpeech();
  applyVoice({ state: "ready" });
}
