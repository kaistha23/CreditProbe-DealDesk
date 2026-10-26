"use client";

/**
 * PLAN_R14 Session E: the engines' (i) content for the deal tiles (K18): RWA and EL with PD, LGD, EAD, the regulatory
 * exposure, the risk weight and every credit-risk mitigant applied, the band test for the rating, and the SVA/RAROC basis.
 * `useEngineEconomics(analysis)` reads POST /engines/{id}/summary for the structure the tile shows (economics, approval path, capacity).
 */

import * as React from "react";

import { useLoad, type Analysis } from "@/lib/v5/dealdesk";
import { enginesApi, type Summary, pct1, sarMn } from "@/lib/v5/dealdesk-engines";

/** The engines' summary of the structure an Analysis shows (null while loading or when the engines cannot read the deal). */
export function useEngineEconomics(a: Analysis | null): Summary | null {
  const key = a ? `eng-sum:${a.proposal_id}:${JSON.stringify(a.terms)}` : "eng-sum:none";
  const r = useLoad(() => (a?.proposal_id ? enginesApi.summary(a.proposal_id, a.terms as unknown as Record<string, unknown>)
                                          : Promise.reject(new Error("no deal"))), key);
  return r.data ?? null;
}

export function RwaElInfo({ e }: { e: Summary }) {
  return (
    <span className="block space-y-1" data-testid="engine-rwa-info">
      <span className="block">{e.rwa.info}</span>
      <span className="block">{e.el.info}</span>
      <span className="block">{e.pd.info}.</span>
      <span className="block">{e.lgd.info}.</span>
      <span className="block">{e.bands.ok ? "Within the band for the rating" : "Outside the band for the rating"}
        {e.bands.el_explained_by ? ` (EL ${e.bands.el_explained_by})` : ""}{e.bands.rwa_explained_by ? ` (RWA ${e.bands.rwa_explained_by})` : ""}. Period: {e.period.label}.</span>
    </span>
  );
}

export function SvaInfo({ e }: { e: Summary }) {
  return (
    <span className="block" data-testid="engine-sva-info">
      SVA, {e.basis.label}: {sarMn(e.sva.lifetime, 2)} = PV of risk-adjusted profit less the {pct1(e.raroc.hurdle)} hurdle charge on capital.
      Year one: {sarMn(e.sva.one_year, 2)} (RAROC {pct1(e.raroc.one_year)}). {e.basis.note}
    </span>
  );
}

export function ApprovalInfo({ e }: { e: Summary }) {
  const ap = e.approval;
  return (
    <span className="block space-y-1" data-testid="engine-approval-info">
      <span className="block font-medium text-text-primary">{ap.rule}</span>
      {ap.reasons.filter((r) => r.detail !== ap.binding.detail).map((r) => <span key={`${r.basis}-${r.detail}`} className="block">Also: {r.detail} → {r.level}</span>)}
      {ap.expected_days.value ? <span className="block">Expected time to decision: about {Math.round(ap.expected_days.value)} days (median of {ap.expected_days.n} past decisions at this level).</span> : null}
      {ap.documents_missing.length ? <span className="block">Documents still missing for the committee pack: {ap.documents_missing.length}.</span> : null}
    </span>
  );
}
