import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { CreditResponseView } from "@/components/v5/dealdesk/credit-response/credit-response";

/** R16 c: Deal Desk → Credit response (business request in, credit division's response out). */
export const dynamic = "force-dynamic";

export default function CreditResponsePage() {
  return (
    <React.Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <CreditResponseView />
    </React.Suspense>
  );
}
