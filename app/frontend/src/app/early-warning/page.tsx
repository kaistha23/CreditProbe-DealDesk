import * as React from "react";

import { EarlyWarningWorkspace } from "@/components/v5/ews/workspace";

/**
 * v5 Early Warning (module 1). Corporate and Retail, on the Early Warning
 * service's own data aligned to the Cockpit books. The view lives in the
 * address, so the page is rendered per request and the part that reads the
 * address has a Suspense boundary of its own.
 */
export const dynamic = "force-dynamic";

export default function EarlyWarningPage() {
  return (
    <React.Suspense fallback={<p className="text-sm text-text-muted">Opening Early Warning…</p>}>
      <EarlyWarningWorkspace />
    </React.Suspense>
  );
}
