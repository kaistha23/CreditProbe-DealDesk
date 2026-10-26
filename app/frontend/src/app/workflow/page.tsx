import * as React from "react";

import { WorkflowPage } from "@/components/v5/admin/pages";

/** Admin -> Workflow (PLAN_R5 A1): data access policies, View as user, approval workflows and their live items. */
export const dynamic = "force-dynamic";

export default function Page() {
  return <React.Suspense fallback={<p className="text-sm text-text-muted">Opening Workflow…</p>}><WorkflowPage /></React.Suspense>;
}
