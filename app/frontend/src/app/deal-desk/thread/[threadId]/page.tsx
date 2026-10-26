"use client";

/**
 * One Deal Desk thread at its own URL (R14 n, K16): every question asked on the Deal Desk landing (or routed here
 * from the Cockpit Ask or Noor) opens a new thread; only questions typed inside it continue it. `?q=` carries the
 * first question once and is removed after it is asked, so a refresh never asks twice.
 */

import { useParams, useSearchParams } from "next/navigation";
import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { DeskThread } from "@/components/v5/dealdesk/desk-thread";
import { threadViewKey } from "@/lib/v5/thread-rule";

function Page() {
  const params = useParams<{ threadId: string }>();
  const search = useSearchParams();
  const threadId = String(params?.threadId ?? "");
  if (!threadId) return null;
  return <DeskThread key={threadViewKey("dealdesk", threadId)} threadId={threadId} first={search.get("q") ?? ""} />;
}

export default function DealDeskThreadPage() {
  return (
    <React.Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <Page />
    </React.Suspense>
  );
}
