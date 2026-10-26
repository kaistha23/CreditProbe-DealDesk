"use client";

import { usePathname, useSearchParams } from "next/navigation";

import { currentHref } from "@/components/v5/mail/share";
import { AddToReportButton } from "@/components/v5/playbook/add-to-report";
import { playbook, type PlaybookSource, type SourceType } from "@/lib/v5/playbook";

/**
 * Add the page being viewed to a Playbook report: Playbook resolves the object (`type`, `id`) into a section with
 * its charts and tables, and the section links back to this exact view.
 */
export function AddCurrentToReport({ type, id, label, testId, defaultTemplate = "credit-committee-pack" }: {
  type: SourceType; id: string; label: string; testId: string; defaultTemplate?: string;
}) {
  const pathname = usePathname();
  const params = useSearchParams();
  const href = currentHref(pathname, params);
  const source: PlaybookSource = { type, id, label, href };
  return (
    <AddToReportButton source={source} testId={testId} defaultTemplate={defaultTemplate} defaultTitle={label}
                       build={async () => {
                         const r = await playbook.section(type, id);
                         return { ...r.section, source: { ...(r.source as PlaybookSource), href } };
                       }} />
  );
}
