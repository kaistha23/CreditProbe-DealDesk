"use client";

/** One validation conversation at its own URL. The id is in the path. */

import { useParams } from "next/navigation";
import * as React from "react";

import { useWideContent } from "@/components/layout/content-width";
import { ScorecardThread } from "@/components/v5/scorecard/thread";
import { threadViewKey } from "@/lib/v5/thread-rule";

export default function ScorecardThreadPage() {
  const params = useParams<{ threadId: string }>();
  useWideContent();
  const threadId = String(params?.threadId ?? "");
  if (!threadId) return null;
  // R16 m (M6): keyed by the thread, so a new thread's ?ask= is asked there, never in the previous thread.
  return <ScorecardThread key={threadViewKey("scorecard", threadId)} threadId={threadId} />;
}
