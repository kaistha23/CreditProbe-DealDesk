"use client";

/**
 * The Cockpit ECL panel's cards open a drawer with their charts (PLAN_R4 B1).
 *
 * EAD, recognised ECL, coverage, every stage row and every component of the ECL movement is a card: clicking it
 * (or Enter / Space on it) opens the same right-side drawer the attention items use, with the card's figures as the
 * panel printed them and the four charts from the attention chart API (backend/attention_v5, families `ecl-ead`,
 * `ecl-total`, `ecl-coverage`, `ecl-stage`, `ecl-component`). The frozen panel only spreads `cards.headline(...)`,
 * `cards.stage(...)` and `cards.component(...)` onto its elements and renders `cards.drawer`; everything else is here.
 */

import * as React from "react";

import type { DomainId, EclPanel as EclPanelBody } from "@/components/cockpit-v4/client";
import { periodLabel } from "@/components/cockpit-v4/period";
import { InfoPopover } from "@/components/ui/info-popover";

import { CardCharts, type ChartRequest } from "./drawer-extras";

interface Num { label: string; display: string }

/** One ECL panel card, as the drawer shows it. */
export interface EclCard { id: string; title: string; subtitle?: string; numbers: Num[]; about?: string; request: ChartRequest }

type Profile = EclPanelBody["profile"] & { display_ead_movement?: string; display_coverage_movement?: string };

function book(domain: DomainId): "corporate" | "retail" {
  return domain === "retail" ? "retail" : "corporate";
}

/** The card spec of a headline figure (`ead`, `ecl`, `coverage`), a stage row, or a decomposition component. */
export function eclCard(domain: DomainId, body: EclPanelBody, what: { headline: "ead" | "ecl" | "coverage" } | { stage: number } | { component: string }): EclCard | null {
  const p = body.profile as Profile;
  const d = body.decomposition;
  const at = { domain: book(domain), period: p.reporting_period, comparison: p.comparison_period };
  const now = p.reporting_period;
  const before = p.comparison_period;
  if ("headline" in what) {
    const spec = {
      ead: { family: "ecl-ead", title: "Exposure at default", numbers: [{ label: `Exposure at default, ${now}`, display: p.display_total_ead },
        ...(p.display_ead_movement ? [{ label: `Movement against ${before}`, display: p.display_ead_movement }] : [])] },
      ecl: { family: "ecl-total", title: "Recognised ECL", numbers: [{ label: `Recognised ECL, ${now}`, display: p.display_total_ecl },
        { label: `Movement against ${before}`, display: p.display_ecl_movement }] },
      coverage: { family: "ecl-coverage", title: "Coverage", numbers: [{ label: `Coverage, ${now}`, display: p.display_coverage },
        { label: `Recognised ECL, ${now}`, display: p.display_total_ecl }, { label: `Exposure at default, ${now}`, display: p.display_total_ead }] },
    }[what.headline];
    return { id: `ecl-${what.headline}`, title: `${p.domain_label}: ${spec.title.toLowerCase()}`, numbers: spec.numbers,
             request: { ...at, family: spec.family, segment: p.domain_label } };
  }
  if ("stage" in what) {
    const s = p.stages.find((x) => x.stage === what.stage);
    if (!s) return null;
    return {
      id: `ecl-stage-${s.stage}`, title: `${p.domain_label}: ${s.label}`,
      numbers: [{ label: `Exposure, ${now}`, display: s.display_ead }, { label: "Share of exposure", display: s.display_share_of_ead },
                { label: `ECL, ${now}`, display: s.display_ecl }, { label: "Coverage", display: s.display_coverage },
                { label: `ECL movement against ${before}`, display: s.display_ecl_movement }],
      request: { ...at, family: "ecl-stage", segment: String(s.stage) },
    };
  }
  const c = d.components.find((x) => x.component_id === what.component);
  if (!c) return null;
  return {
    id: `ecl-component-${c.component_id}`, title: `${p.domain_label}: ${c.label.toLowerCase()}`, about: c.explanation,
    numbers: [{ label: `Contribution to the ECL movement, ${before} to ${now}`, display: c.display_amount },
              { label: "Total ECL movement", display: d.display_movement }],
    request: { ...at, family: "ecl-component", segment: c.component_id },
  };
}

/** The drawer one ECL panel card opens: its figures, then its four charts. Close with ✕ or Escape. */
export function EclCardDrawer({ card, onClose, periods }: { card: EclCard | null; onClose: () => void; periods: string }) {
  React.useEffect(() => {
    if (!card) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [card, onClose]);
  if (!card) return null;
  return (
    <aside data-testid="ecl-card-drawer" data-card-id={card.id} aria-label={card.title}
           className="fixed right-0 top-0 z-40 flex h-full w-full max-w-2xl flex-col overflow-y-auto border-l border-border bg-surface shadow-xl">
      <header className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-border bg-surface px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold text-text-primary" data-testid="ecl-card-drawer-title">{card.title}</h2>
          <p className="mt-0.5 text-xs text-text-muted">{periods}</p>
        </div>
        <button type="button" onClick={onClose} data-testid="ecl-card-drawer-close" aria-label="Close"
                className="rounded px-2 py-1 text-sm text-text-muted hover:bg-surface-sunken">✕</button>
      </header>
      <div className="space-y-5 px-5 py-4 text-sm text-text-secondary">
        {card.about ? <p data-testid="ecl-card-drawer-about">{card.about}</p> : null}
        <section data-testid="ecl-card-drawer-numbers">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">Key numbers</h3>
          <dl className="mt-1 divide-y divide-border">
            {card.numbers.map((n) => (
              <div key={n.label} className="flex items-baseline justify-between gap-4 py-1.5">
                <dt className="text-xs text-text-muted">{n.label}</dt>
                <dd className="font-mono text-sm text-text-primary">{n.display}</dd>
              </div>
            ))}
          </dl>
        </section>
        <CardCharts request={card.request} />
      </div>
    </aside>
  );
}

/** For the frozen ECL panel: props that make an element a card that opens its drawer, and the drawer itself. */
export function useEclCards(domain: DomainId, body: EclPanelBody | null) {
  const [open, setOpen] = React.useState<EclCard | null>(null);
  React.useEffect(() => { setOpen(null); }, [domain]);
  const close = React.useCallback(() => setOpen(null), []);
  const props = (spec: EclCard | null) => spec ? {
    role: "button" as const, tabIndex: 0, "aria-haspopup": "dialog" as const, "data-chart-card": spec.id,
    style: { cursor: "pointer" },
    onClick: () => setOpen(spec),
    onKeyDown: (e: React.KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(spec); } },
  } : {};
  const periods = body ? `${periodLabel(body.profile.reporting_period)} vs ${periodLabel(body.profile.comparison_period)}` : "";
  return {
    headline: (key: string) => props(body ? eclCard(domain, body, { headline: key as "ead" | "ecl" | "coverage" }) : null),
    stage: (stage: number) => props(body ? eclCard(domain, body, { stage }) : null),
    component: (id: string) => props(body ? eclCard(domain, body, { component: id }) : null),
    drawer: <EclCardDrawer card={open} onClose={close} periods={periods} />,
  };
}

/** The panel's method and notes, behind an (i) instead of under the tables (G1). */
export function EclPanelInfo({ body }: { body: EclPanelBody }) {
  return (
    <InfoPopover title="How these figures are computed" className="align-middle">
      <p>{body.profile.note}</p>
      <p>{body.decomposition.method}</p>
    </InfoPopover>
  );
}

/** An (i) holding a note that used to be printed inline (G1). Renders nothing when there is no note. */
export function InfoNote({ title, children }: { title: string; children: React.ReactNode }) {
  if (!children) return null;
  return <InfoPopover title={title} className="ml-1.5 align-middle font-normal normal-case tracking-normal">{children}</InfoPopover>;
}
