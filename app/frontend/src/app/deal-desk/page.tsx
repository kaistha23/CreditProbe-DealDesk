import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { DealDeskHome } from "@/components/v5/dealdesk/home";

/**
 * v5 Deal Desk (Pre-deal Analysis, DEAL_DESK_PROMPT section 4): the chat box
 * at the top and the proposal pipeline below it, on the Deal Desk service
 * (port 8508). Selecting a proposal opens its thread.
 */
export const dynamic = "force-dynamic";

export default function DealDeskPage() {
  return (
    <React.Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <DealDeskHome />
    </React.Suspense>
  );
}
