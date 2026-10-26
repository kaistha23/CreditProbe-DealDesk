import * as React from "react";

import { PlaybookScreen } from "@/components/v5/playbook/home";
import { Loading } from "@/components/v5/workspace/parts";

/**
 * v5 Playbook (PLAN_R3, S1): committee packs, risk reports, credit memos, scenario and validation
 * reports, on the Playbook service (backend.playbook_v5.api, port 8506). `/playbook` is the home;
 * `/playbook?report=<id>[&section=<sid>][&version=<n>]` opens one report. The part that reads the
 * address has a Suspense boundary of its own.
 */
export default function PlaybookPage() {
  return (
    <React.Suspense fallback={<Loading what="Opening Playbook…" />}>
      <PlaybookScreen />
    </React.Suspense>
  );
}
