"use client";

/**
 * Round P: a deal flagged by an approved regulation or policy (Policy Docs): the check it fails and the clause cited.
 * Renders nothing when the deal has no open flag.
 */

import Link from "next/link";
import * as React from "react";
import { Scale } from "lucide-react";

import { type Flag, rulebook } from "@/lib/v5/dealdesk-rules";

export function PolicyFlags({ proposalId }: { proposalId: string }) {
  const [flags, setFlags] = React.useState<Flag[]>([]);
  React.useEffect(() => {
    let live = true;
    rulebook.deal(proposalId).then((r) => live && setFlags(r.flags), () => undefined);
    return () => { live = false; };
  }, [proposalId]);
  if (!flags.length) return null;
  return (
    <div className="mb-2 flex items-start gap-2 rounded-lg border border-warning/40 bg-warning-muted px-3 py-2 text-[12.5px]" role="status" data-testid="deal-policy-flags">
      <Scale className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
      <div className="min-w-0">
        <p className="font-semibold text-text-primary">Flagged by policy: {flags.length} check{flags.length === 1 ? "" : "s"} fail under a newly applied requirement</p>
        <ul className="mt-0.5 space-y-0.5 text-text-secondary">
          {flags.map((f) => (
            <li key={f.n} data-testid="deal-policy-flag" data-check={f.check_id}>
              {f.label}: {f.why} — <span className="font-medium text-text-primary">{f.reference} {f.clause}</span>{" "}
              <Link href={`/policy-docs?view=regulation`} className="text-accent hover:underline">Policy Docs</Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
