import { BackButton } from "@/components/v5/core/back-button";
import * as React from "react";

import { EwsModelCard } from "@/components/v5/ews/model-card";

/**
 * Early Warning model card: the rule set as a standard model card for a
 * credit-committee reader -- summary, inputs by source and risk layer, score
 * bands, calibration and performance, limitations and version log -- served
 * live from the Early Warning backend (GET /api/v1/ews/model-card).
 */
export const dynamic = "force-dynamic";

export default async function EarlyWarningModelPage({ searchParams }: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const domain = sp.domain === "retail" ? "retail" : "corporate";
  const period = typeof sp.period === "string" && /^[0-9A-Za-z-]+$/.test(sp.period) ? sp.period : "";
  return (
    <div className="space-y-4">
      {/* R7: the exact previous screen (the Early Warning view it was opened from, drill and period included). */}
      <BackButton fallback={{ href: `/early-warning?domain=${domain}${period ? `&period=${period}` : ""}`, label: "Early Warning" }}
                  testId="ews-model-back" />
      <React.Suspense fallback={<p className="text-sm text-text-muted">Opening the model card…</p>}>
        <EwsModelCard />
      </React.Suspense>
    </div>
  );
}
