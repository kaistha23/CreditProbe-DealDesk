"use client";

/**
 * One What-If conversation at its own URL. The id is in the path, the
 * question never is: a run is started before the navigation and this page
 * finds it running and follows it, so a refresh never asks twice.
 */

import { useParams } from "next/navigation";
import * as React from "react";

import { useWideContent } from "@/components/layout/content-width";
import { WhatIfThread } from "@/components/v5/whatif/thread";
import { threadViewKey } from "@/lib/v5/thread-rule";

export default function WhatIfThreadPage() {
  const params = useParams<{ threadId: string }>();
  useWideContent();
  const threadId = String(params?.threadId ?? "");
  if (!threadId) return null;
  // R16 m (M6): keyed by the thread, so another thread never shows (or continues) this one's turns.
  return <WhatIfThread key={threadViewKey("whatif", threadId)} threadId={threadId} />;
}
