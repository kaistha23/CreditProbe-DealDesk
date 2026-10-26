import * as React from "react";

import { PolicyDocsRoute } from "@/components/v5/policy/library";
import { Loading } from "@/components/v5/workspace/parts";

/**
 * v5 Policy Docs (PLAN_R3 S1-2): every credit policy document and circular, stored and versioned, and the
 * active policy pack the Cockpit cites, on the Playbook and Policy Docs service (port 8506). The view lives in
 * the address (?doc=<id>&clause=<clause id> opens one document), so the page is rendered per request and the
 * part that reads the address has a Suspense boundary of its own.
 */
export const dynamic = "force-dynamic";

export default function PolicyDocsPage() {
  return (
    <React.Suspense fallback={<Loading what="Opening Policy Docs…" />}>
      <PolicyDocsRoute />
    </React.Suspense>
  );
}
