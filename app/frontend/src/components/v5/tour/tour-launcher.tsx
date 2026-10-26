"use client";

/**
 * "Take the tour" (PLAN_R14 session t, K36; R15 a, L1): the header button is the ONLY way the tour starts. There is no
 * first-sign-in prompt, no `?tour=1` link and no start-from-anywhere event: a tour never starts over someone's work.
 * Mounted once in the app header; the player renders over every page and survives navigation because the header does.
 * `?tour_speed=` (walk-throughs) only shortens each line once the button has started the tour.
 */
import * as React from "react";
import { Compass } from "lucide-react";

import { useCoreAuth } from "@/components/v5/core/auth";

import { LABELS, tourSpeed, type TourLang } from "./tour-model";
import { TourPlayer } from "./tour-player";

const LANG_KEY = "cp.tour.lang";

function readLang(): TourLang {
  try { return window.localStorage.getItem(LANG_KEY) === "ar" ? "ar" : "en"; } catch { return "en"; }
}

function LauncherInner() {
  const { status } = useCoreAuth();
  const [open, setOpen] = React.useState(false);
  const [lang, setLang] = React.useState<TourLang>("en");
  const [speed, setSpeed] = React.useState(1);

  // L1: the one start path, the button's own click.
  const start = React.useCallback(() => {
    setLang(readLang());
    setSpeed(tourSpeed(window.location.search));
    setOpen(true);
  }, []);

  if (status !== "authenticated") return null;
  return (
    <>
      <button type="button" onClick={start} data-testid="tour-take" data-tour="tour-take"
              title={LABELS.en.take}
              className="hidden h-8 items-center gap-1.5 rounded-md px-2 text-[12.5px] font-medium text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary md:inline-flex">
        <Compass className="size-[15px]" aria-hidden />
        <span className="hidden xl:inline">{LABELS.en.take}</span>
      </button>
      {open ? (
        <TourPlayer lang={lang} speed={speed}
                    onLang={(l) => { setLang(l); try { window.localStorage.setItem(LANG_KEY, l); } catch { /* ok */ } }}
                    onClose={() => setOpen(false)} />
      ) : null}
    </>
  );
}

export function TourLauncher() {
  return <React.Suspense fallback={null}><LauncherInner /></React.Suspense>;
}
