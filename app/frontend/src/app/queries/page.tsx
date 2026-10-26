import { redirect } from "next/navigation";

import { REMOVED_ROUTES } from "@/lib/navigation";

/** PLAN_R10 S1: /queries redirects to /: queries are answered in the Cockpit (Session Q wires the capability there); the Queries components stay for that. */
export const dynamic = "force-dynamic";

export default function RemovedScreen() {
  redirect(REMOVED_ROUTES["/queries"] ?? "/");
}
