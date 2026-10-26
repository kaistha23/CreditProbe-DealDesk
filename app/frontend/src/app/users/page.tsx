import * as React from "react";

import { UsersPage } from "@/components/v5/admin/pages";

/** Admin -> Users and Teams (PLAN_R5 Session A), served by the Admin service (port 8510). */
export const dynamic = "force-dynamic";

export default function Page() {
  return <React.Suspense fallback={<p className="text-sm text-text-muted">Opening Users and Teams…</p>}><UsersPage /></React.Suspense>;
}
