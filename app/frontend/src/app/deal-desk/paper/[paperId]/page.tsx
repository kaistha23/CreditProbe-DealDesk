"use client";

/** Rounds W/T: one living document (credit proposal or business request) at its own URL, reopened from Recent work, the deal's
 *  Papers and the Workspace. ?view=provenance opens the Provenance view; ?section=<key> points Noor at a section. */

import { useParams, useSearchParams } from "next/navigation";
import * as React from "react";

import { useWideContent } from "@/components/layout/content-width";
import { Skeleton } from "@/components/ui/skeleton";
import { ProposalWorkspace } from "@/components/v5/dealdesk/paperws";

function Paper() {
  const params = useParams<{ paperId: string }>();
  const q = useSearchParams();
  const id = decodeURIComponent(String(params?.paperId ?? ""));
  if (!id) return null;
  return <ProposalWorkspace key={id} wsId={id} initialView={q.get("view") === "provenance" ? "provenance" : "document"} initialFocus={q.get("section") || undefined} />;
}

export default function PaperPage() {
  useWideContent();
  return (
    <React.Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <Paper />
    </React.Suspense>
  );
}
