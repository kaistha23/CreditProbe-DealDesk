import { redirect } from "next/navigation";

import { REMOVED_ROUTES } from "@/lib/navigation";

/** PLAN_R10 S1: /accepted-risk redirects to /early-warning: Accepted Risk Watch is not a separate screen; its watch status stays as a filter or tag in Early Warning and Borrower 360. */
export const dynamic = "force-dynamic";

export default function RemovedScreen() {
  redirect(REMOVED_ROUTES["/accepted-risk"] ?? "/early-warning");
}
