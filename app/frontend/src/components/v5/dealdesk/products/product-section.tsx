"use client";

/**
 * PLAN_R12 Session P: the deal page's product slot (Session U's `Product` slot, props { proposalId }). Reads the deal's
 * product template and which product sections have data (GET /products/{id}/sections) and mounts them: contracting →
 * ProjectSection, escrow → EscrowSection, syndicated → SyndicationSection, sme → SmeFastTrack on this application.
 * A corporate deal with no product data renders nothing.
 */

import * as React from "react";

import { productsApi, useProduct } from "./api";
import { EscrowSection } from "./escrow-section";
import { ProjectSection } from "./project-section";
import { SmeFastTrack } from "./sme-fast-track";
import { SyndicationSection } from "./syndication-section";

export function ProductSection({ proposalId, onOpenFullFlow }: {
  proposalId: string;
  onOpenFullFlow?: (route: { applicationId: string; proposalId: string | null; reasons: string[] }) => void;
}) {
  const { data } = useProduct(`sections:${proposalId}`, (s) => productsApi.sections(proposalId, s));
  if (!data || !data.sections.length) return null;
  return (
    <div className="min-w-0 space-y-4" data-testid="products-section">
      {data.sections.map((s) =>
        s === "project" ? <ProjectSection key={s} proposalId={proposalId} />
          : s === "escrow" ? <EscrowSection key={s} proposalId={proposalId} />
            : s === "syndication" ? <SyndicationSection key={s} proposalId={proposalId} />
              : s === "sme" ? <SmeFastTrack key={s} applicationId={proposalId} onOpenFullFlow={onOpenFullFlow} /> : null)}
    </div>
  );
}
