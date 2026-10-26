import * as React from "react";

import { VoiceSampler } from "@/components/noor/voice-sampler";

/** Settings -> Voice (PLAN_R15 a, L2): the voice buffet; the chosen voice per language becomes the bank's default. */
export const dynamic = "force-dynamic";

export default function Page() {
  return <React.Suspense fallback={<p className="text-sm text-text-muted">Opening Voice…</p>}><VoiceSampler /></React.Suspense>;
}
