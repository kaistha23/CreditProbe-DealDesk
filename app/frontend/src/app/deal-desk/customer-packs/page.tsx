import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { CustomerPacksPage } from "@/components/v5/dealdesk/customer-packs";

/** R16 d: Deal Desk → Customer packs (reached from the proposal list). */
export const dynamic = "force-dynamic";

export default function CustomerPacks() {
  return (
    <React.Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <CustomerPacksPage />
    </React.Suspense>
  );
}
