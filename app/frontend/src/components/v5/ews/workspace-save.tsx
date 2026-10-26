"use client";

/**
 * Early Warning: Save as investigation (PLAN_R3 S3-2). Saves the level the reader is on as a thread: the view as the
 * question, the service's commentary and headline as the answer, with the headline figures and the top warning
 * reasons as artifacts, and a link back to the same view to continue.
 */

import { usePathname, useSearchParams } from "next/navigation";

import { currentHref } from "@/components/v5/mail/share";
import { SaveButton } from "@/components/v5/workspace/save";
import type { Level } from "@/lib/v5/ews";
import { ws3 } from "@/lib/v5/workspace-r3";

export function EwsSaveInvestigation({ level, testId = "ews-save-investigation" }: { level: Level; testId?: string }) {
  const pathname = usePathname();
  const params = useSearchParams();
  const href = currentHref(pathname, params);
  const h = level.headline;
  const L = level.labels;
  const save = (title: string) => ws3.importInvestigation({
    source: { type: "early-warning-level", id: `${level.domain_id}|${level.period}|${level.name}`,
              label: `Early Warning · ${level.name}`, href },
    title, continue_href: href, period: level.period,
    turns: [
      { role: "user", text: `Early Warning: ${level.name}, ${level.period}. What is building and why?` },
      { role: "assistant", text: [level.interpretation?.headline, level.interpretation?.interpretation, level.commentary].filter(Boolean).join("\n\n"),
        artifacts: [
          { kind: "figures", title: `${level.name}, ${level.period}`, period: level.period, figures: [
            { key: "customers", label: L.owners, value: h.customers, unit: "int" },
            { key: "customers_warned", label: `Warned ${L.owners}`, value: h.customers_warned, unit: "int" },
            { key: "high_or_critical", label: "High or critical", value: h.high_or_critical, unit: "int" },
            { key: "exposure", label: "Exposure", value: h.exposure, unit: "sar_mn" },
            { key: "ecl", label: "ECL", value: h.ecl, unit: "sar_mn" },
            { key: "exposure_severe", label: "High/critical exposure", value: h.exposure_severe, unit: "sar_mn" },
          ] },
          { kind: "table", title: "Top warning reasons", period: level.period,
            columns: [{ key: "reason", label: "Reason", unit: "text" }, { key: "customers", label: L.owners, unit: "int" },
                      { key: "exposure", label: "Exposure", unit: "sar_mn" }],
            rows: level.top_reasons.slice(0, 15).map((r) => ({ reason: r.name || r.reason, customers: r.customers, exposure: r.exposure })) },
          { kind: "object", type: "early-warning-list", id: level.name, label: `Early Warning · ${level.name}`, href },
        ] },
    ],
  });
  return <SaveButton kind="investigation" testId={testId} defaultTitle={`${level.name}: Early Warning, ${level.period}`} save={save} />;
}
