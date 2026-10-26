import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { OnboardPage } from "@/components/v5/dealdesk/onboard-page";

/** PLAN_R11 P6: Deal Desk Parameters → Learn from documents. */
export const dynamic = "force-dynamic";

export default function LearnFromDocuments() {
  return (
    <React.Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <OnboardPage />
    </React.Suspense>
  );
}
