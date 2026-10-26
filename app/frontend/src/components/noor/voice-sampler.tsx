"use client";

/**
 * Settings → Voice (R15 a, L2): a buffet of voices to listen to before one is put into CreditProbe.
 *
 * Every English and Arabic voice this computer gives the browser (Mac system voices; Enhanced, Premium and Siri voices
 * where the system exposes them), male and female, reads the same two or three sentences of today's real brief. Rate
 * and pitch sliders per language. "Use for English" / "Use for Arabic" makes that voice (with its rate and pitch) the
 * bank's default, read by Noor and the tour. R16 M1: until a voice is chosen Noor and the tour stay silent in that
 * language; voices are listed best first (Premium, Enhanced, Siri, Natural/neural, Google, plain) with a quality label. Mac voices worth downloading
 * and cloud neural voices are listed as options with a clear label, never played here.
 *
 * R16 v: beside each language's browser voices, the offline NEURAL voices (the add-on on this computer: Kokoro for
 * English, male and female; Piper ar_JO Kareem for Arabic) read the same lines through /api/v1/voice/speak, side by side,
 * so Anne can compare and pick. With the add-on absent they are listed with what to install, and Listen is off.
 * Nothing speaks unless Listen is clicked (M1).
 *
 * R16 v2: grouped by language and accent. Under each language, after the existing tables, a table per regional accent
 * (Indian English; Arabic – Saudi; Arabic – UAE (Gulf)): the Mac voices the browser exposes for that locale, the
 * expected Mac voices that are missing, why there is no offline neural voice, and the optional cloud voices (Azure),
 * labelled "Cloud – text leaves the machine; demo with fictional data only", each with Listen and Use for … and
 * whether it plays on this computer and why not (voice-regions.ts).
 */

import * as React from "react";
import { Check, Play, Square } from "lucide-react";

import { Card } from "@/components/ui/card";
import { useCoreAuth } from "@/components/v5/core/auth";
import { AdminFrame, Chip } from "@/components/v5/admin/frame";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";

import { noor } from "./noor-client";
import type { NoorSettings } from "./noor-model";
import { noorWiring, stopSpeaking, useNoor } from "./noor-store";
import { loadVoices, speechSupported, stopSpeech } from "./noor-voice";
import {
  type NeuralStatus, type NeuralVoice, CLOUD_LABEL, NEURAL_INSTALL_HINT, neuralCandidates, neuralLabel, neuralStatus, speakNeural,
} from "./neural-voice";
import { type Region, type RegionalRow, REGIONS, offlineNote, playId, regionSummary, regionalRows } from "./voice-regions";
import {
  type Candidate, type ChoiceLang, type Chosen, type ChosenVoice, CHOICE_LANGS, OTHER_OPTIONS, PITCH, QUALITY_LABEL, RATE,
  candidates, choiceLine, clamp, isNeural, missingDownloads, normaliseChosen, resolveChosen, sampleLines, writeChosen,
} from "./voice-choice";

const LANG_LABEL: Record<ChoiceLang, string> = { "en": "English", "ar-gulf": "Arabic" };
const GENDER_LABEL = { male: "Male", female: "Female", unknown: "Not stated" } as const;

function useVoices(): { voices: SpeechSynthesisVoice[]; ready: boolean } {
  const [voices, setVoices] = React.useState<SpeechSynthesisVoice[]>([]);
  const [ready, setReady] = React.useState(false);
  React.useEffect(() => {
    let alive = true;
    void loadVoices(3000).then((v) => { if (alive) { setVoices(v); setReady(true); } });
    const s = typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null;
    const onChange = () => { if (s && alive) setVoices(s.getVoices()); };
    s?.addEventListener?.("voiceschanged", onChange);
    return () => { alive = false; s?.removeEventListener?.("voiceschanged", onChange); };
  }, []);
  return { voices, ready };
}

export function VoiceSampler() {
  const { isAdmin } = useCoreAuth();
  const { settings } = useNoor();
  const { voices, ready } = useVoices();
  const [chosen, setChosen] = React.useState<Chosen>(() => normaliseChosen(settings.voice?.chosen));
  const [rate, setRate] = React.useState<Record<ChoiceLang, number>>({ "en": RATE.start, "ar-gulf": RATE.start });
  const [pitch, setPitch] = React.useState<Record<ChoiceLang, number>>({ "en": PITCH.start, "ar-gulf": PITCH.start });
  const [lines, setLines] = React.useState<Record<ChoiceLang, string>>({ "en": sampleLines("", "en"), "ar-gulf": sampleLines("", "ar-gulf") });
  const [source, setSource] = React.useState("fixed sample lines (the brief could not be read)");
  const [playing, setPlaying] = React.useState<string>("");
  const [msg, setMsg] = React.useState("");
  const [err, setErr] = React.useState("");
  const [neural, setNeural] = React.useState<NeuralStatus | null>(null);
  const [neuralMsg, setNeuralMsg] = React.useState("");

  // The bank's settings (fresh), so the page shows the current choice and its rate and pitch.
  React.useEffect(() => {
    let alive = true;
    noor.settings().then((s) => {
      if (!alive) return;
      noorWiring.setSettings(s);
      const c = normaliseChosen(s.voice?.chosen);
      setChosen(c);
      setRate((r) => ({ "en": c.en?.rate ?? r.en, "ar-gulf": c["ar-gulf"]?.rate ?? r["ar-gulf"] }));
      setPitch((p) => ({ "en": c.en?.pitch ?? p.en, "ar-gulf": c["ar-gulf"]?.pitch ?? p["ar-gulf"] }));
    }, () => undefined);
    // The same lines of today's real brief for every voice (its spoken script, two or three sentences).
    noor.brief({}).then((b) => {
      if (!alive) return;
      setLines({ "en": sampleLines(b.script?.en || b.opening, "en"), "ar-gulf": sampleLines(b.script?.ar || b.opening_ar, "ar-gulf") });
      setSource(`today's brief (${b.date_label || b.date})`);
    }, () => undefined);
    // R16 v: which neural voices the add-on has (no model is loaded and nothing is spoken here).
    void neuralStatus(true).then((st) => { if (alive) setNeural(st); });
    return () => { alive = false; stopSpeech(); };
  }, []);

  const all = React.useMemo(() => candidates(voices), [voices]);
  const missing = React.useMemo(() => missingDownloads(voices), [voices]);

  const play = (c: Candidate | Candidate[]) => {
    const list = Array.isArray(c) ? c : [c];
    const s = typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null;
    if (!s) return;
    stopSpeaking();
    s.cancel();
    if (!list.length) return;
    list.forEach((one, i) => {
      const v = voices.find((x) => x.name === one.name && x.lang === one.lang);
      if (!v) return;
      const u = new SpeechSynthesisUtterance(lines[one.group]);
      u.voice = v;
      u.lang = v.lang;
      u.rate = rate[one.group];
      u.pitch = pitch[one.group];
      u.onstart = () => setPlaying(`${one.name}|${one.lang}`);
      u.onend = () => { if (i === list.length - 1) setPlaying(""); };
      u.onerror = () => { if (i === list.length - 1) setPlaying(""); };
      s.speak(u);
    });
  };
  const stop = () => { stopSpeech(); setPlaying(""); };

  /** R16 v: a neural voice reads the same lines (Listen click only); `rest` follows, one after another. */
  const playNeural = async (v: NeuralVoice, rest: NeuralVoice[] = []) => {
    stopSpeaking();
    stopSpeech();
    setNeuralMsg("");
    const id = `neural|${v.id}`;
    setPlaying(id);
    const o = await speakNeural(lines[v.group], v.id, v.lang, rate[v.group], { start: () => setPlaying(id) });
    if (o === "absent") { setNeuralMsg(`The neural add-on is not answering. ${NEURAL_INSTALL_HINT}`); setNeural(await neuralStatus(true)); }
    if (o === "failed") setNeuralMsg(`${v.name} could not be played here.`);
    if (o === "ended" && rest.length) { void playNeural(rest[0], rest.slice(1)); return; }
    setPlaying((p) => (p === id ? "" : p));
  };

  const save = (group: ChoiceLang, c: Candidate | null) => saveChoice(group, c ? `${c.name}` : "",
    c ? { name: c.name, lang: c.lang, rate: clamp(rate[group], RATE), pitch: clamp(pitch[group], PITCH) } : null);
  const saveNeural = (group: ChoiceLang, v: NeuralVoice) => saveChoice(group, neuralLabel(v),
    { engine: "neural", name: v.id, lang: v.lang, label: neuralLabel(v), rate: clamp(rate[group], RATE), pitch: clamp(pitch[group], PITCH) });

  const saveChoice = async (group: ChoiceLang, label: string, value: ChosenVoice | null) => {
    setErr("");
    setMsg("");
    const c = value ? { name: label } : null;
    try {
      const saved = await noor.saveSettings({ voice: { chosen: { [group]: value } } } as unknown as Partial<NoorSettings>);
      noorWiring.setSettings(saved);
      const n = normaliseChosen(saved.voice?.chosen);
      setChosen(n);
      writeChosen(n);
      setMsg(c ? `${c.name} is now the ${LANG_LABEL[group]} voice for Noor and the tour.` : `${LANG_LABEL[group]} voice cleared: not chosen.`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Not saved.");
    }
  };

  const plain = [
    "Listen to each voice read the same lines of today's brief, in English and Arabic, then pick one per language.",
    "The voice you pick, with its speed and pitch, becomes the bank's default for Noor and the tour.",
    "Until a voice is picked Noor stays silent; it speaks only when you press a speaker.",
    "Beside them are the offline neural voices: they sound like a person and run on this computer; no text leaves it.",
    "Voices not on this computer are listed below with how to get them; nothing is installed from here.",
  ];

  return (
    <AdminFrame eyebrow="Settings" title="Voice" testId="voice-sampler"
                info={<p>A voice buffet: every voice the browser can use on this computer reads the same sentences of today&apos;s brief.
                  Choose one per language; the choice (with rate and pitch) becomes Noor&apos;s and the tour&apos;s voice for the bank.
                  Speech is the browser&apos;s own: no text leaves the computer for system voices.</p>}
                seeds={[{ label: "Which voice should Noor use?", send: "How do I choose Noor's voice in Settings?" }]}>
      <PlainWords lines={plain} testId="voice-plain-words" />
      <div className="grid gap-3 lg:grid-cols-2" data-testid="voice-chosen">
        {CHOICE_LANGS.map((g) => {
          const installed = Boolean(resolveChosen(voices, chosen[g])) || isNeural(chosen[g]);
          return (
            <Card key={g} className="space-y-1 p-4" data-testid={`voice-chosen-${g}`} data-chosen={chosen[g] ? "true" : "false"}>
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">{LANG_LABEL[g]} voice</p>
              <p className="text-[13px] text-text-primary">{choiceLine(chosen[g], installed || !ready, g)}</p>
              {chosen[g] && isAdmin ? (
                <button type="button" onClick={() => void save(g, null)} data-testid={`voice-clear-${g}`}
                        className="text-[11.5px] text-text-muted hover:text-text-primary hover:underline">Clear the choice</button>) : null}
            </Card>);
        })}
      </div>
      {msg ? <p className="text-[12px] text-positive" role="status" data-testid="voice-msg">{msg}</p> : null}
      {err ? <p className="text-[12px] text-negative" role="alert">{err}</p> : null}
      {!isAdmin ? <p className="text-[12px] text-text-muted">Listen to any voice; an administrator makes the choice for the bank.</p> : null}
      {!speechSupported() && ready ? <p className="text-[12px] text-negative" role="status">This browser cannot read aloud.</p> : null}

      {CHOICE_LANGS.map((g) => (
        <section key={g} className="space-y-2" data-testid={`voice-group-${g}`}>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-[15px] font-semibold text-text-primary">{LANG_LABEL[g]} voices on this computer
                <span className="ml-2 text-[12px] font-normal text-text-muted">{ready ? `${all[g].length} found` : "reading the voices…"}</span></h2>
              <p className="mt-0.5 max-w-[760px] text-[12px] text-text-secondary" dir={g === "ar-gulf" ? "rtl" : "ltr"} lang={g === "ar-gulf" ? "ar" : "en"}
                 data-testid={`voice-sample-${g}`}>&ldquo;{lines[g]}&rdquo;</p>
              <p className="text-[11px] text-text-muted">The same lines for every voice, from {source}.</p>
            </div>
            <div className="flex flex-wrap items-center gap-4 text-[12px]">
              <Slider label="Rate" value={rate[g]} r={RATE} onChange={(v) => setRate({ ...rate, [g]: v })} testId={`voice-rate-${g}`} />
              <Slider label="Pitch" value={pitch[g]} r={PITCH} onChange={(v) => setPitch({ ...pitch, [g]: v })} testId={`voice-pitch-${g}`} />
              <button type="button" onClick={() => (playing ? stop() : play(all[g]))} disabled={!all[g].length} data-testid={`voice-play-all-${g}`}
                      className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-[12px] text-text-secondary hover:border-accent disabled:opacity-40">
                {playing ? <Square size={13} /> : <Play size={13} />} {playing ? "Stop" : "Listen to all, one after another"}</button>
            </div>
          </div>
          <h3 className="text-[13px] font-semibold text-text-primary" data-testid={`voice-accent-main-${g}`}>
            {g === "en" ? "English – US / UK" : "Arabic – Jordan (Kareem) and Modern Standard"}
            <span className="ml-2 text-[11.5px] font-normal text-text-muted">with every {LANG_LABEL[g]} voice of this browser</span></h3>
          <div className="grid gap-3 min-[1800px]:grid-cols-2" data-testid={`voice-side-by-side-${g}`}>
          <NeuralTable group={g} status={neural} chosen={chosen[g]} playing={playing} isAdmin={isAdmin} rate={rate[g]}
                       onListen={(v) => (playing === `neural|${v.id}` ? stop() : void playNeural(v))}
                       onListenAll={(list) => (playing.startsWith("neural|") ? stop() : list.length ? void playNeural(list[0], list.slice(1)) : undefined)}
                       onUse={(v) => void saveNeural(g, v)} />
          <div className="min-w-0 space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">Browser and Mac voices</p>
          <div className="overflow-x-auto rounded-md border border-border bg-surface">
            <table className="w-full text-[12.5px]" data-testid={`voice-table-${g}`}>
              <thead className="bg-surface-sunken text-left text-[10px] uppercase tracking-wide text-text-muted">
                <tr><th className="px-3 py-2">Voice</th><th className="px-3 py-2">Voice type</th><th className="px-3 py-2">Quality</th>
                  <th className="px-3 py-2">Language</th><th className="px-3 py-2">Where it runs</th><th className="px-3 py-2" /></tr>
              </thead>
              <tbody>
                {all[g].map((c) => {
                  const id = `${c.name}|${c.lang}`;
                  const isChosen = !isNeural(chosen[g]) && chosen[g]?.name === c.name && chosen[g]?.lang === c.lang;
                  return (
                    <tr key={id} className={cn("border-t border-border", isChosen && "bg-accent/5")} data-testid="voice-row" data-voice={c.name}
                        data-gender={c.gender} data-quality={c.quality}>
                      <td className="px-3 py-2 font-medium text-text-primary">{c.name}{isChosen ? <span className="ml-2"><Chip tone="accent">Chosen</Chip></span> : null}</td>
                      <td className="px-3 py-2">{GENDER_LABEL[c.gender]}</td>
                      <td className="px-3 py-2">{c.quality === "standard" ? QUALITY_LABEL.standard : <Chip tone="good">{QUALITY_LABEL[c.quality]}</Chip>}</td>
                      <td className="px-3 py-2 font-mono text-[11.5px]">{c.lang}</td>
                      <td className="px-3 py-2 text-text-secondary">{c.source}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-right">
                        <button type="button" onClick={() => (playing === id ? stop() : play(c))} data-testid="voice-listen"
                                className="mr-2 inline-flex h-7 items-center gap-1 rounded-md border border-border px-2.5 text-[12px] hover:border-accent">
                          {playing === id ? <Square size={12} /> : <Play size={12} />} {playing === id ? "Stop" : "Listen"}</button>
                        {isAdmin ? (
                          <button type="button" onClick={() => void save(g, c)} disabled={isChosen && chosen[g]?.rate === rate[g] && chosen[g]?.pitch === pitch[g]}
                                  data-testid="voice-use"
                                  className="inline-flex h-7 items-center gap-1 rounded-md bg-accent px-2.5 text-[12px] font-medium text-accent-contrast disabled:opacity-40">
                            <Check size={12} /> {isChosen ? "Keep this rate and pitch" : `Use for ${LANG_LABEL[g]}`}</button>) : null}
                      </td>
                    </tr>);
                })}
                {ready && !all[g].length ? (
                  <tr><td colSpan={6} className="px-3 py-3 text-text-muted" data-testid={`voice-none-${g}`}>
                    No {LANG_LABEL[g]} voice is installed in this browser. Download one below, then reload this page.</td></tr>) : null}
              </tbody>
            </table>
          </div>
          </div>
          </div>
          {neuralMsg ? <p className="text-[12px] text-negative" role="status">{neuralMsg}</p> : null}
          {REGIONS.filter((r) => r.group === g).map((r) => (
            <RegionalTable key={r.id} region={r} rows={regionalRows(r, voices, neural)} status={neural} ready={ready}
                           chosen={chosen[g]} playing={playing} isAdmin={isAdmin} rate={rate[g]} pitch={pitch[g]}
                           onListen={(row) => (playing === playId(row) ? stop() : row.kind === "mac" ? play(macCandidate(row, g)) : row.voice ? void playNeural(row.voice) : undefined)}
                           onUse={(row) => (row.kind === "mac" ? void save(g, macCandidate(row, g)) : row.voice ? void saveNeural(g, row.voice) : undefined)} />))}
        </section>))}

      <section className="space-y-2" data-testid="voice-options">
        <h2 className="text-[15px] font-semibold text-text-primary">More voices, not installed</h2>
        <p className="text-[12px] text-text-secondary">Listed so you can weigh them. None plays here and none is used until it is installed and chosen.</p>
        <div className="grid gap-3 lg:grid-cols-2">
          <Card className="space-y-1.5 p-4" data-testid="voice-mac-downloads">
            <p className="text-[13px] font-semibold text-text-primary">Mac voices to download</p>
            <p className="text-[11.5px] text-text-muted">System Settings → Accessibility → Spoken Content → System voice → Manage Voices; then reload this page.
              Siri voices appear only where macOS lets the browser use them.</p>
            {missing.length ? <ul className="space-y-0.5 text-[12px]">{missing.map((d) => (
              <li key={d.name} data-testid="voice-download">{d.name} <span className="text-text-muted">· {LANG_LABEL[d.group]} · {GENDER_LABEL[d.gender].toLowerCase()} · not on this computer</span></li>))}</ul>
              : <p className="text-[12px] text-text-secondary">Every suggested Mac voice is already installed.</p>}
          </Card>
          {(["cloud"] as const).map((k) => (
            <Card key={k} className="space-y-1.5 p-4" data-testid={`voice-options-${k}`}>
              <p className="text-[13px] font-semibold text-text-primary">Cloud neural voices (not set up)</p>
              <p className="text-[11.5px] text-text-muted">Sends the text out of the bank to a speech service. For demos only; never for client data.
                The offline neural voices above sound as natural and keep the text on this computer. The Saudi, Emirati and Indian
                cloud voices are in their accent tables above{neural?.cloud?.configured ? ` (cloud on, region ${neural.cloud.region})` : " (cloud off here)"}.</p>
              <ul className="space-y-1 text-[12px]">{OTHER_OPTIONS.filter((o) => o.kind === k).map((o) => (
                <li key={o.id} data-testid="voice-option" data-kind={o.kind}>
                  <span className="text-text-primary">{o.name}</span>
                  <span className="text-text-muted"> · {LANG_LABEL[o.group]} · {GENDER_LABEL[o.gender].toLowerCase()}</span>
                  <span className="ml-1"><Chip tone="warn">Sends text out · demo only</Chip></span>
                </li>))}</ul>
            </Card>))}
        </div>
      </section>
    </AdminFrame>
  );
}

/** R16 v: the offline neural voices for one language, beside the browser's voices. */
function NeuralTable({ group, status, chosen, playing, isAdmin, rate, onListen, onListenAll, onUse }: {
  group: ChoiceLang; status: NeuralStatus | null; chosen: ChosenVoice | null; playing: string; isAdmin: boolean; rate: number;
  onListen: (v: NeuralVoice) => void; onListenAll: (list: NeuralVoice[]) => void; onUse: (v: NeuralVoice) => void;
}) {
  const list = neuralCandidates(status?.voices ?? [], group);
  const engine = group === "ar-gulf" ? "piper" : "kokoro";
  const on = Boolean(status?.engines?.[engine]);
  const what = group === "ar-gulf" ? "Piper, ar_JO Kareem" : "Kokoro-82M";
  return (
    <div className="min-w-0 space-y-1" data-testid={`voice-neural-${group}`} data-available={on ? "true" : "false"}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">Neural voices, offline on this computer ({what})</p>
        <button type="button" onClick={() => onListenAll(list)} disabled={!on || !list.length} data-testid={`voice-neural-play-all-${group}`}
                className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2.5 text-[12px] text-text-secondary hover:border-accent disabled:opacity-40">
          {playing.startsWith("neural|") ? <Square size={12} /> : <Play size={12} />} {playing.startsWith("neural|") ? "Stop" : "Listen to all"}</button>
      </div>
      <p className="text-[11.5px] text-text-secondary" data-testid="voice-piper-note">
        {status === null ? "Checking the neural voice add-on…"
          : on ? `Installed. Runs on this computer: no text leaves it. Speed ${rate.toFixed(2)} (the Rate slider); pitch is the voice's own.`
          : `Not installed here${status.reached ? "" : " (the Deal Desk service did not answer)"}. ${NEURAL_INSTALL_HINT}`}
      </p>
      <div className="overflow-x-auto rounded-md border border-border bg-surface">
        <table className="w-full text-[12.5px]" data-testid={`voice-neural-table-${group}`}>
          <thead className="bg-surface-sunken text-left text-[10px] uppercase tracking-wide text-text-muted">
            <tr><th className="px-3 py-2">Voice</th><th className="px-3 py-2">Voice type</th><th className="px-3 py-2">Sound</th>
              <th className="px-3 py-2" /></tr>
          </thead>
          <tbody>
            {list.map((v) => {
              const id = `neural|${v.id}`;
              const isChosen = isNeural(chosen) && chosen.name === v.id;
              return (
                <tr key={v.id} className={cn("border-t border-border", isChosen && "bg-accent/5")} data-testid="voice-neural-row"
                    data-voice={v.id} data-gender={v.gender}>
                  <td className="px-3 py-2 font-medium text-text-primary">{v.name}
                    <span className="ml-1.5 text-[11px] font-normal text-text-muted">{v.accent} · <span className="font-mono">{v.lang}</span></span>
                    {isChosen ? <span className="ml-2"><Chip tone="accent">Chosen</Chip></span> : null}</td>
                  <td className="px-3 py-2">{GENDER_LABEL[v.gender]}</td>
                  <td className="px-3 py-2"><Chip tone="good">Neural</Chip> <span className="text-[11.5px] text-text-muted">{v.note}</span></td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">
                    <button type="button" onClick={() => onListen(v)} disabled={!on} data-testid="voice-neural-listen"
                            className="mr-2 inline-flex h-7 items-center gap-1 rounded-md border border-border px-2.5 text-[12px] hover:border-accent disabled:opacity-40">
                      {playing === id ? <Square size={12} /> : <Play size={12} />} {playing === id ? "Stop" : "Listen"}</button>
                    {isAdmin ? (
                      <button type="button" onClick={() => onUse(v)} disabled={!on || (isChosen && chosen?.rate === rate)} data-testid="voice-neural-use"
                              className="inline-flex h-7 items-center gap-1 rounded-md bg-accent px-2.5 text-[12px] font-medium text-accent-contrast disabled:opacity-40">
                        <Check size={12} /> {isChosen ? "Keep this speed" : `Use for ${LANG_LABEL[group]}`}</button>) : null}
                  </td>
                </tr>);
            })}
            {status !== null && !list.length ? (
              <tr><td colSpan={4} className="px-3 py-3 text-text-muted">No neural voice listed: the Deal Desk service did not answer.</td></tr>) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** R16 v2: a regional Mac row as the browser table's candidate (same play and save path). */
function macCandidate(r: RegionalRow, g: ChoiceLang): Candidate {
  return { name: r.name, lang: r.lang, group: g, gender: r.gender, quality: r.quality ?? "standard", local: true, source: "" };
}

/** R16 v2: one regional accent (Indian English; Arabic – Saudi; Arabic – UAE (Gulf)): every source, with whether it
 *  plays on this computer and why not. */
function RegionalTable({ region, rows, status, ready, chosen, playing, isAdmin, rate, pitch, onListen, onUse }: {
  region: Region; rows: RegionalRow[]; status: NeuralStatus | null; ready: boolean; chosen: ChosenVoice | null; playing: string;
  isAdmin: boolean; rate: number; pitch: number; onListen: (r: RegionalRow) => void; onUse: (r: RegionalRow) => void;
}) {
  const lang = LANG_LABEL[region.group];
  const cloudOn = Boolean(status?.cloud?.configured);
  const offline = rows.some((r) => r.kind === "offline");
  return (
    <div className="min-w-0 space-y-1 pt-2" data-testid={`voice-region-${region.id}`} data-region={region.id}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[13px] font-semibold text-text-primary">{region.title}
          <span className="ml-2 font-mono text-[11px] font-normal text-text-muted">{region.id}</span></h3>
        <p className="text-[11.5px] text-text-secondary" data-testid="voice-region-summary">
          {ready && status !== null ? regionSummary(rows) : "checking this computer…"}</p>
      </div>
      {!offline ? <p className="text-[11.5px] text-text-muted" data-testid="voice-region-offline-note">Offline neural: {offlineNote(region, status)}</p> : null}
      <div className="overflow-x-auto rounded-md border border-border bg-surface">
        <table className="w-full text-[12.5px]" data-testid={`voice-region-table-${region.id}`}>
          <thead className="bg-surface-sunken text-left text-[10px] uppercase tracking-wide text-text-muted">
            <tr><th className="px-3 py-2">Voice</th><th className="px-3 py-2">Voice type</th><th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">On this computer</th><th className="px-3 py-2" /></tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const pid = playId(r);
              const isChosen = Boolean(chosen && (r.kind === "mac"
                ? !isNeural(chosen) && chosen.name === r.name && chosen.lang === r.lang
                : isNeural(chosen) && chosen.name === r.voice?.id));
              const same = isChosen && chosen?.rate === rate && (r.kind !== "mac" || chosen?.pitch === pitch);
              return (
                <tr key={r.key} className={cn("border-t border-border", isChosen && "bg-accent/5")} data-testid="voice-region-row"
                    data-kind={r.kind} data-voice={r.voice?.id ?? r.name} data-gender={r.gender} data-available={r.available ? "true" : "false"}>
                  <td className="px-3 py-2 font-medium text-text-primary">{r.name}
                    <span className="ml-1.5 font-mono text-[11px] font-normal text-text-muted">{r.lang}</span>
                    {isChosen ? <span className="ml-2"><Chip tone="accent">Chosen</Chip></span> : null}</td>
                  <td className="px-3 py-2">{GENDER_LABEL[r.gender]}</td>
                  <td className="px-3 py-2">
                    {r.kind === "mac" ? <span>Mac system voice{r.quality && r.quality !== "standard" ? <> <Chip tone="good">{QUALITY_LABEL[r.quality]}</Chip></> : null}</span>
                      : r.kind === "offline" ? <Chip tone="good">Offline neural</Chip>
                      : <span data-testid="voice-cloud-label"><Chip tone="warn">{r.label || CLOUD_LABEL}</Chip></span>}
                  </td>
                  <td className="px-3 py-2 text-[11.5px]" data-testid="voice-region-why">
                    {r.available ? <span className="text-positive">Available{r.why ? ` · ${r.why}` : ""}</span>
                      : <span className="text-text-muted">{r.why}</span>}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">
                    <button type="button" onClick={() => onListen(r)} disabled={!r.available} data-testid="voice-region-listen"
                            className="mr-2 inline-flex h-7 items-center gap-1 rounded-md border border-border px-2.5 text-[12px] hover:border-accent disabled:opacity-40">
                      {playing === pid ? <Square size={12} /> : <Play size={12} />} {playing === pid ? "Stop" : "Listen"}</button>
                    {isAdmin ? (
                      <button type="button" onClick={() => onUse(r)} disabled={!r.available || same} data-testid="voice-region-use"
                              className="inline-flex h-7 items-center gap-1 rounded-md bg-accent px-2.5 text-[12px] font-medium text-accent-contrast disabled:opacity-40">
                        <Check size={12} /> {isChosen ? "Keep these settings" : `Use for ${lang}`}</button>) : null}
                  </td>
                </tr>);
            })}
          </tbody>
        </table>
      </div>
      {rows.some((r) => r.kind === "cloud") && !cloudOn ? (
        <p className="text-[11px] text-text-muted" data-testid="voice-cloud-how">{status?.cloud?.how_to_enable
          ?? "Cloud voices are off unless the Deal Desk service has CP_TTS_CLOUD_KEY and CP_TTS_CLOUD_REGION."}</p>) : null}
    </div>
  );
}

function Slider({ label, value, r, onChange, testId }: {
  label: string; value: number; r: { min: number; max: number; step: number }; onChange: (v: number) => void; testId: string;
}) {
  return (
    <label className="inline-flex items-center gap-2 text-text-secondary">
      {label}
      <input type="range" min={r.min} max={r.max} step={r.step} value={value} data-testid={testId}
             onChange={(e) => onChange(Number(e.target.value))} className="w-28 accent-current" />
      <span className="w-9 tabular-nums text-text-primary">{value.toFixed(2)}</span>
    </label>
  );
}
