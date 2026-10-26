"use client";

/**
 * PLAN_R10 L1 (docs/v5/R10_FEEDBACK.md): the small mark under the Sign in button, with "AI powered" beneath it.
 *
 * The image is Anne's chosen mark, served from `/brand/ai-powered-mark.png` (the orchestrator commits the file).
 * It sits on an ivory rounded tile (#F5F3EE, the image's own background) so it reads the same in light and dark
 * themes. Until the file is there, or if it fails to load, an elegant typographic fallback takes its place: the
 * same ivory tile with a navy "AI" monogram. No animation (reduced motion needs nothing).
 */

import * as React from "react";

import { cn } from "@/lib/utils";

export const AI_MARK_SRC = "/brand/ai-powered-mark.png";
/** The mark's tile: about 56–64 px (R10_FEEDBACK L1). */
export const AI_MARK_SIZE = 60;

export function AiPoweredMark({ className, src = AI_MARK_SRC }: { className?: string; src?: string }) {
  const [failed, setFailed] = React.useState(false);
  const img = React.useRef<HTMLImageElement>(null);

  // An error that fired before hydration never reaches onError: check the element once mounted.
  React.useEffect(() => {
    const el = img.current;
    if (el && el.complete && el.naturalWidth === 0) setFailed(true);
  }, []);

  return (
    <figure className={cn("flex flex-col items-center gap-1.5", className)} data-testid="login-ai-mark"
            data-mark={failed ? "fallback" : "image"}>
      <span className="flex items-center justify-center overflow-hidden rounded-xl bg-[#F5F3EE] shadow-sm ring-1 ring-border"
            style={{ width: AI_MARK_SIZE, height: AI_MARK_SIZE }}>
        {failed ? (
          <span aria-hidden data-testid="login-ai-mark-fallback"
                className="display select-none text-[20px] font-semibold tracking-[0.04em] text-[#1F2A44]">
            AI
          </span>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element -- a static brand file; next/image adds nothing at 60 px
          <img ref={img} src={src} alt="" width={AI_MARK_SIZE} height={AI_MARK_SIZE} decoding="async"
               className="size-full object-contain" onError={() => setFailed(true)} />
        )}
      </span>
      <figcaption className="text-[11px] uppercase tracking-[0.12em] text-text-muted">AI powered</figcaption>
    </figure>
  );
}
