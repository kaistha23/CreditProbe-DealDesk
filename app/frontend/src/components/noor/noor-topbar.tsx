"use client";

/**
 * Noor in the top bar (PLAN_R12 N1): the "Viewing as" switch (demo and admin accounts only), the "Ask Noor" button
 * top right on every screen, and the side panel it opens. Mounted by one line in `components/layout/header.tsx`.
 *
 * It also wires the shared thread to the page: the router (Show me navigates with the panel open), the module the
 * reader is on, the persona, the bank's name and voice settings, and the Cockpit attention cards (read through the
 * Cockpit's own client, unchanged, as evidence for the brief). On the first sign-in of the day the brief is shown first
 * (R16 M1: shown, never spoken; speech only from a speaker click).
 */

import * as React from "react";

import { edition } from "@/lib/navigation";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { readAttention } from "@/components/cockpit-v4/client";
import { useCoreAuth } from "@/components/v5/core/auth";
import { cn } from "@/lib/utils";

import { noor } from "./noor-client";
import { moduleOf } from "./noor-model";
import { NoorMark, NoorPanel } from "./noor-panel";
import { loadBrief, noorWiring, openPanel, prepareVoice, togglePanel, useNoor } from "./noor-store";
import { VoiceChoiceNote } from "./speaker-button";
import { ViewingAsSwitch, useViewingAs } from "./viewing-as";

export function NoorTopBar() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const fromBell = params.get("noor") === "brief";
  const { status, user } = useCoreAuth();
  const { persona } = useViewingAs();
  const s = useNoor();
  const [ready, setReady] = React.useState(false);

  React.useEffect(() => { noorWiring.setNavigate((href) => router.push(href)); }, [router]);
  // Chrome fills its voice list late (voiceschanged): start reading it as soon as the shell is up (J1).
  React.useEffect(() => { prepareVoice(); }, []);
  React.useEffect(() => { noorWiring.setModule(moduleOf(pathname)); }, [pathname]);
  React.useEffect(() => { noorWiring.setPersona(persona); }, [persona]);
  React.useEffect(() => {
    noorWiring.setAttentionReader(async () => {
      const feed = await readAttention("corporate");
      return (feed?.segments_requiring_attention ?? []) as unknown[];
    });
    return () => noorWiring.setAttentionReader(null);
  }, []);
  React.useEffect(() => {
    if (status !== "authenticated" || !user) return;
    noorWiring.setUser(user.username);
    let live = true;
    noor.settings().then((cfg) => { if (live) { noorWiring.setSettings(cfg); setReady(true); } },
                         () => { if (live) setReady(true); });
    return () => { live = false; };
  }, [status, user]);

  // The bell's "your brief for today" notification opens the panel on the brief.
  React.useEffect(() => {
    if (ready && fromBell) void loadBrief();
  }, [ready, fromBell]);

  // The brief speaks first: once per person per day, on the first screen after signing in.
  React.useEffect(() => {
    if (!ready || !user || !s.settings.speak_first || pathname === "/login") return;
    const key = `noor.spoke.${user.username}.${new Date().toISOString().slice(0, 10)}`;
    try {
      if (window.localStorage.getItem(key)) return;
      window.localStorage.setItem(key, "1");
    } catch { return; }
    // On Home the Brief tab already shows the brief, so the panel stays closed there (R13 H, J2). R16 M1: the brief is
    // shown, never spoken: nothing is read aloud on sign-in.
    if (!fromBell) void loadBrief({ open: pathname !== "/", ...(edition() === "dealdesk" ? { module: "dealdesk" } : {}) });  // the bell's link opens it already
  }, [ready, user, s.settings.speak_first, pathname, fromBell]);

  // K7: the N key opens Noor on a fresh thread (not while typing in a box).
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "n" && e.key !== "N") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      e.preventDefault();
      openPanel(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (status !== "authenticated") return null;
  return (
    <>
      <ViewingAsSwitch />
      <button type="button" onClick={togglePanel} aria-expanded={s.open} data-testid="ask-noor"
              title={`Ask ${s.settings.name} (N): a new thread on this page; earlier threads under the clock`}
              className={cn("flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-[12.5px] font-medium transition-colors",
                s.open ? "border-accent bg-accent text-accent-contrast" : "border-accent/50 text-accent hover:bg-accent/10")}>
        <NoorMark className={cn("size-5", s.open && "bg-white/20 text-accent-contrast")} />
        Ask {s.settings.name}
      </button>
      <NoorPanel />
      <VoiceChoiceNote />
    </>
  );
}
