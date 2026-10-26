import * as React from "react";

import { BrfStudio } from "@/components/v5/brf/studio";
import { Loading } from "@/components/v5/workspace/parts";

/**
 * v5 BRF studio (PLAN_R10 Session B, item 13): a chat box (attach a template, "complete all data for this template")
 * and an editable React Flow flowchart of sources → calculations → checks → output lines; Lock → Run → Publish,
 * on the Queries and BRF service (port 8516). `/brf?r=R1` opens that quick start.
 */
export const dynamic = "force-dynamic";

export default function BrfPage() {
  return (
    <React.Suspense fallback={<Loading what="Opening the BRF studio…" />}>
      <BrfStudio />
    </React.Suspense>
  );
}
