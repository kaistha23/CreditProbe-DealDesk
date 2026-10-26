import * as React from "react";

import { SettingsPage } from "@/components/v5/admin/pages";

/** Admin -> Settings (PLAN_R5 Session A), served by the Admin service (port 8510). */
export const dynamic = "force-dynamic";

export default function Page() {
  return <React.Suspense fallback={<p className="text-sm text-text-muted">Opening Settings…</p>}><SettingsPage /></React.Suspense>;
}
