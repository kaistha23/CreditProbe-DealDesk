import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { RarocDriftPage } from "@/components/v5/dealdesk/portfolio-raroc";

/** PLAN_R12 I7: Deal Desk → Book → RAROC drift (renamed from Portfolio RAROC at origination). */
export const dynamic = "force-dynamic";

export default function RarocDrift() {
  return (
    <React.Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <RarocDriftPage />
    </React.Suspense>
  );
}
