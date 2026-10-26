import * as React from "react";

import { ScorecardHome } from "@/components/v5/scorecard/home";

/**
 * v5 Scorecard Validation (PLAN_R3 S2): a chat box that opens a thread, and the past validations below it.
 * Served by the Scorecard service (port 8507). Opened with ?validation=<id> it goes to that validation's thread.
 */
export const dynamic = "force-dynamic";

export default function ScorecardValidationPage() {
  return (
    <React.Suspense fallback={<p className="text-sm text-text-muted">Opening Scorecard Validation…</p>}>
      <ScorecardHome />
    </React.Suspense>
  );
}
