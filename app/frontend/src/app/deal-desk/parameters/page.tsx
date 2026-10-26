import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { DeskParametersPage } from "@/components/v5/dealdesk/desk-parameters";

/** PLAN_R9 E1: Admin → Deal Desk Parameters. */
export const dynamic = "force-dynamic";

export default function DeskParameters() {
  return (
    <React.Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <DeskParametersPage />
    </React.Suspense>
  );
}
