"use client";

/**
 * Noor's settings (I13.1): the assistant's name and voice are bank settings (Gulf Arabic or English), changed by an
 * administrator and read by everyone. R15 a (L2): the voice itself is chosen in Settings -> Voice (one per language,
 * with its rate and pitch); until then the R14 interim pick (male, calm) reads and says "not chosen yet". A one-time
 * note says how to download the Enhanced voices on the Mac. Voice uses the browser's own speech: nothing is installed.
 */

import * as React from "react";
import { useRouter } from "next/navigation";

import { useCoreAuth } from "@/components/v5/core/auth";

import { noor } from "./noor-client";
import type { NoorSettings } from "./noor-model";
import { noorWiring, setVoiceLanguage, setVoiceOn, speakerButton, useNoor } from "./noor-store";
import { voiceStateLabel } from "./noor-voice";

export function NoorSettingsForm() {
  const { isAdmin } = useCoreAuth();
  const { settings, voice: mine } = useNoor();
  const router = useRouter();
  const [draft, setDraft] = React.useState<NoorSettings>(settings);
  const [msg, setMsg] = React.useState("");
  const voice = draft.voice;
  const save = async () => {
    try {
      const saved = await noor.saveSettings(draft);
      noorWiring.setSettings(saved);
      setMsg("Saved for the bank.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Not saved.");
    }
  };
  return (
    <div className="space-y-4">
    <EnhancedVoiceNote />
    <fieldset className="space-y-2.5 text-[12.5px]" data-testid="noor-my-voice">
      <legend className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted">My voice</legend>
      <label className="flex items-center justify-between gap-3">
        <span className="text-text-secondary">Read aloud</span>
        <input type="checkbox" checked={mine.on} data-testid="noor-my-voice-on" onChange={(e) => setVoiceOn(e.target.checked)} />
      </label>
      <label className="flex items-center justify-between gap-3">
        <span className="text-text-secondary">Language</span>
        <select value={mine.language} data-testid="noor-my-voice-language"
                onChange={(e) => setVoiceLanguage(e.target.value as "en" | "ar-gulf")}
                className="h-8 w-40 rounded border border-border bg-canvas px-2 text-text-primary">
          <option value="en">English</option><option value="ar-gulf">Arabic</option>
        </select>
      </label>
      <p className="flex items-center justify-between gap-3 text-[11.5px] text-text-muted">
        <span data-testid="noor-my-voice-state" data-fixed={mine.fixed ? "true" : "false"}>{mine.state === "speaking" ? "Reading…"
          : mine.voiceName && mine.state !== "no-voice" ? `Voice: ${mine.voiceName} (chosen)` : voiceStateLabel(mine.state, mine.on, mine.language)}</span>
        <button type="button" onClick={() => speakerButton(null)} disabled={mine.state === "unsupported"}
                className="shrink-0 rounded-md border border-border px-3 py-1 text-[12px] text-text-secondary disabled:opacity-40">
          Try the voice</button>
      </p>
      {/* R15 a (L2): the voice buffet in Settings -> Voice; the voice chosen there is Noor's and the tour's. */}
      <button type="button" onClick={() => router.push("/settings/voice")} data-testid="noor-choose-voice"
              className="text-[12px] font-medium text-accent hover:underline">Listen to every voice and choose one (Settings → Voice)</button>
    </fieldset>
    <form className="space-y-2.5 text-[12.5px]" data-testid="noor-settings" onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted">Assistant settings (bank)</p>
      <label className="flex items-center justify-between gap-3">
        <span className="text-text-secondary">Name</span>
        <input value={draft.name} disabled={!isAdmin} maxLength={24} data-testid="noor-settings-name"
               onChange={(e) => setDraft({ ...draft, name: e.target.value })}
               className="h-8 w-40 rounded border border-border bg-canvas px-2 text-text-primary disabled:opacity-60" />
      </label>
      <label className="flex items-center justify-between gap-3">
        <span className="text-text-secondary">Voice on for new readers</span>
        <input type="checkbox" checked={voice.enabled} disabled={!isAdmin} data-testid="noor-settings-voice"
               onChange={(e) => setDraft({ ...draft, voice: { ...voice, enabled: e.target.checked } })} />
      </label>
      <p className="flex items-center justify-between gap-3">
        <span className="text-text-secondary">Voice</span>
        <span className="w-40 text-text-primary" data-testid="noor-settings-gender">Chosen in Settings → Voice</span>
      </p>
      <label className="flex items-center justify-between gap-3">
        <span className="text-text-secondary">Language</span>
        <select value={voice.language} disabled={!isAdmin}
                onChange={(e) => setDraft({ ...draft, voice: { ...voice, language: e.target.value as "en" | "ar-gulf" } })}
                className="h-8 w-40 rounded border border-border bg-canvas px-2 text-text-primary disabled:opacity-60">
          <option value="en">English</option><option value="ar-gulf">Gulf Arabic</option>
        </select>
      </label>
      <label className="flex items-center justify-between gap-3">
        <span className="text-text-secondary">Brief speaks first on sign-in</span>
        <input type="checkbox" checked={draft.speak_first} disabled={!isAdmin}
               onChange={(e) => setDraft({ ...draft, speak_first: e.target.checked })} />
      </label>
      <div className="flex items-center gap-2">
        {isAdmin ? (
          <button type="submit" className="rounded-md bg-accent px-3 py-1 text-[12px] font-medium text-accent-contrast">Save</button>
        ) : <span className="text-text-muted">An administrator changes these.</span>}
        {msg ? <span className="text-text-muted">{msg}</span> : null}
      </div>
    </form>
    </div>
  );
}

const NOTE_KEY = "noor.enhanced-voice-note.v1";

function readNoteSeen(): boolean {
  try { return window.localStorage.getItem(NOTE_KEY) === "1"; } catch { return false; }
}

/** One-time note (K10): the Mac's Enhanced or Premium voices sound far more natural than the compact ones. */
export function EnhancedVoiceNote() {
  const [dismissed, setDismissed] = React.useState(false);
  const stored = React.useSyncExternalStore(() => () => undefined, readNoteSeen, () => true);
  if (stored || dismissed) return null;
  const dismiss = () => {
    try { window.localStorage.setItem(NOTE_KEY, "1"); } catch { /* ignore */ }
    setDismissed(true);
  };
  return (
    <div className="rounded-md border border-accent/30 bg-accent/5 px-3 py-2 text-[12px] text-text-secondary" role="note"
         data-testid="noor-enhanced-voice-note">
      <p className="font-medium text-text-primary">For the most natural voice</p>
      <p className="mt-0.5">On a Mac: System Settings → Accessibility → Spoken Content → System voice → Manage Voices.
        Download <b>Evan (Enhanced)</b> or <b>Nathan (Enhanced)</b> for English and <b>Maged</b> for Arabic, then reload
        this page. Then choose one in Settings → Voice.</p>
      <button type="button" onClick={dismiss} data-testid="noor-enhanced-voice-note-ok"
              className="mt-1 text-[11.5px] font-medium text-accent hover:underline">Got it</button>
    </div>
  );
}
