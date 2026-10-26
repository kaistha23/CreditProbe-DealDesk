import * as React from "react";

import { MyRulesPage } from "@/components/v5/rules/my-rules-page";

/** Round K: Deal Desk → My rules (the analyst's profile of writing rules). */
export const dynamic = "force-dynamic";

export default function Page() {
  return (
    <React.Suspense fallback={<p className="text-sm text-text-muted">Opening your rules…</p>}>
      <MyRulesPage />
    </React.Suspense>
  );
}
