"use client";

/** One deal at its own URL: the stepper, the analysis and the conversation. */

import { useParams } from "next/navigation";
import * as React from "react";

import { useWideContent } from "@/components/layout/content-width";
import { Skeleton } from "@/components/ui/skeleton";
import { DealThread } from "@/components/v5/dealdesk/thread";
import { PolicyFlags } from "@/components/v5/rules/policy-flags";

export default function DealPage() {
  const params = useParams<{ proposalId: string }>();
  useWideContent();
  const id = decodeURIComponent(String(params?.proposalId ?? ""));
  if (!id) return null;
  return (
    <React.Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <PolicyFlags proposalId={id} />{/* Round P: flags from an approved regulation or policy */}
      <DealThread proposalId={id} />
    </React.Suspense>
  );
}
