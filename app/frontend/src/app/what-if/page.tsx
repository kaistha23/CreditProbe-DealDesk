import * as React from "react";

import { WhatIfHome } from "@/components/v5/whatif/home";

/**
 * v5 What-If (PLAN_R2 item 6): a chat box that opens a thread, and the scenario
 * library below it. Conversational, on the What-If IFRS 9 domain, through the
 * What-If service (port 8503). Opened with ?cohort=<id> from Early Warning, it
 * opens a thread on exactly that cohort.
 */
export const dynamic = "force-dynamic";

export default function WhatIfPage() {
  return (
    <React.Suspense fallback={<p className="text-sm text-text-muted">Opening What-If…</p>}>
      <WhatIfHome />
    </React.Suspense>
  );
}
