"use client";

/**
 * The module brief (I13.6, first layer): what matters in this module today, from its agent's sources, ranked the
 * same way as the morning brief. Mounted by one line at the top of Deal Desk (by U), Early Warning, What-If and
 * Lenses. Every line has Why? / What should we do? / Show me / Open, answered in Noor's panel. The existing screen
 * stays underneath; a brief that cannot be read shows nothing rather than an error.
 */

import * as React from "react";

import { noor } from "./noor-client";
import type { Brief } from "./noor-model";
import { NoorBrief } from "./noor-brief";
import { useViewingAs } from "./viewing-as";

export type NoorModule = "dealdesk" | "ews" | "whatif" | "lenses";

export function NoorModuleBrief({ module, limit = 3 }: { module: NoorModule; limit?: number }) {
  const { persona } = useViewingAs();
  const [brief, setBrief] = React.useState<Brief | null>(null);
  React.useEffect(() => {
    let live = true;
    noor.brief({ persona, module, top: 5 }).then((b) => { if (live) setBrief(b); }, () => { if (live) setBrief(null); });
    return () => { live = false; };
  }, [persona, module]);
  if (!brief || !brief.items.length) return null;
  return (
    <div className="mb-6 rounded-lg border border-border bg-surface px-4 py-3" data-testid={`noor-module-brief-${module}`}>
      <NoorBrief brief={brief} variant="module" limit={limit} testId="noor-module-lines" />
    </div>
  );
}
