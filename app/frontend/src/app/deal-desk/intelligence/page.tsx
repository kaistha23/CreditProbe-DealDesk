import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { IntelligenceStudioPage } from "@/components/v5/dealdesk/intelligence-studio";

/** Round S: Deal Desk → Intelligence Studio (reached from Deal Desk's home and from Agent Operations). */
export const dynamic = "force-dynamic";

export default function IntelligenceStudio() {
  return (
    <React.Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <IntelligenceStudioPage />
    </React.Suspense>
  );
}
