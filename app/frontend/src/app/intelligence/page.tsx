import { redirect } from "next/navigation";

import { REMOVED_ROUTES } from "@/lib/navigation";

/** PLAN_R10 S1: /intelligence redirects to /: the Intelligence Library left the navigation (Anne: "useless"); the packs' "Powered by" lines stay on each screen. */
export const dynamic = "force-dynamic";

export default function RemovedScreen() {
  redirect(REMOVED_ROUTES["/intelligence"] ?? "/");
}
