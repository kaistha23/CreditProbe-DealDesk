import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { ProposalReviewPage } from "@/components/v5/dealdesk/proposal-review";

/** PLAN_R9 E3: Deal Desk → Proposal review (P7 Proposal Intelligence). */
export const dynamic = "force-dynamic";

export default function ProposalReview() {
  return (
    <React.Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <ProposalReviewPage />
    </React.Suspense>
  );
}
