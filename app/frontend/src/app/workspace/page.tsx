import * as React from "react";

import { Loading } from "@/components/v5/workspace/parts";
import { WorkspaceHome } from "@/components/v5/workspace/home";

/**
 * v5 My workspace and Inbox (Phase F), on the Workspace service
 * (backend/workspace_v5, port 8505). The tab lives in the address (?tab=inbox),
 * so the part that reads it has a Suspense boundary of its own.
 */
export default function WorkspacePage() {
  return (
    <React.Suspense fallback={<Loading what="Opening your workspace…" />}>
      <WorkspaceHome />
    </React.Suspense>
  );
}
