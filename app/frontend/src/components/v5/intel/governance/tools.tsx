"use client";

/**
 * R13 IE: the governance tools menu (Admin header and Deal Desk header) and the drawer that shows one compact panel.
 * Nothing is added to the first screen but this one button (PLAN_R13 mantra). ?gov=<panel>[&q=…] opens a panel
 * directly, which is how Noor's intents (lib/v5/intel-intents.ts) land here.
 */

import * as React from "react";
import { Landmark, X } from "lucide-react";

import { Dropdown } from "@/components/v5/ui/dropdown"; // R14 U (K28)
import { type GovOrigin, type GovPanel, parseGovPanel } from "@/lib/v5/intel-governance";
import { GOVERNANCE_INTENTS, type IntelMenu } from "@/lib/v5/intel-intents-ie";

import { DoaPanel } from "./doa-panel";
import { ExceptionPanel } from "./exception-panel";
import { InspectionPanel } from "./inspection-panel";
import { RmTrackPanel } from "./rm-track-panel";
import { GovOriginContext } from "./shared";

function readUrl(): { panel: GovPanel | null; q: string } {
  if (typeof window === "undefined") return { panel: null, q: "" };
  const u = new URL(window.location.href);
  return { panel: parseGovPanel(u.searchParams.get("gov")), q: u.searchParams.get("q") ?? "" };
}

function writeUrl(panel: GovPanel | null) {
  try {
    const u = new URL(window.location.href);
    if (panel) u.searchParams.set("gov", panel); else { u.searchParams.delete("gov"); u.searchParams.delete("q"); }
    window.history.replaceState(window.history.state, "", u.toString());
  } catch { /* the drawer still opens */ }
}

export function GovernancePanel({ panel, q = "" }: { panel: GovPanel; q?: string }) {
  switch (panel) {
    case "inspection": return <InspectionPanel initial={q} />;
    case "exceptions": return <ExceptionPanel />;
    case "rm-track": return <RmTrackPanel />;
    case "doa": return <DoaPanel />;
  }
}

export function GovernanceDrawer({ panel, q, onClose }: { panel: GovPanel; q?: string; onClose: () => void }) {
  const intent = GOVERNANCE_INTENTS.find((i) => i.id === panel)!;
  React.useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={intent.label} data-testid={`gov-drawer-${panel}`} data-tour={panel === "inspection" ? "gov-inspection" : undefined}>
      <button type="button" aria-label="Close" className="absolute inset-0 bg-black/25" onClick={onClose} tabIndex={-1} />
      <aside className="relative flex h-full w-[min(780px,calc(100vw-2rem))] flex-col border-l border-border bg-surface shadow-xl">
        <header className="flex items-start gap-3 border-b border-border px-5 py-3">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Governance</p>
            <h2 className="text-[17px] font-semibold text-text-primary">{intent.label}</h2>
            <p className="text-[12px] text-text-secondary">{intent.job}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close panel" data-testid="gov-drawer-close"
                  className="ml-auto rounded-md p-1.5 text-text-muted hover:bg-surface-hover hover:text-text-primary"><X size={16} /></button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4"><GovernancePanel panel={panel} q={q} /></div>
      </aside>
    </div>
  );
}

/** The header button: a short menu of the four governance tools; picking one opens its panel in the drawer. */
export function GovernanceTools({ origin, menu }: { origin: GovOrigin; menu: IntelMenu }) {
  const [panel, setPanel] = React.useState<GovPanel | null>(null);
  const [q, setQ] = React.useState("");
  React.useEffect(() => {
    const t = window.setTimeout(() => { const u = readUrl(); if (u.panel) { setPanel(u.panel); setQ(u.q); } }, 0);
    return () => window.clearTimeout(t);
  }, []);
  const pick = (p: GovPanel) => { setQ(""); setPanel(p); writeUrl(p); };
  const close = React.useCallback(() => { setPanel(null); writeUrl(null); }, []);
  const items = GOVERNANCE_INTENTS.filter((i) => i.menus.includes(menu));
  return (
    <GovOriginContext.Provider value={origin}>
      {/* R14 U (K28): the house dropdown */}
      <Dropdown label="Governance" icon={<Landmark />} buttonTestId="gov-tools" menuTestId="gov-tools-menu" width={340}
                sections={[{ items: items.map((i) => ({ key: i.id, label: i.label, description: i.job, testId: `gov-tool-${i.id}`,
                                                       onSelect: () => pick(i.id as GovPanel) })) }]} />
      {panel ? <GovernanceDrawer panel={panel} q={q} onClose={close} /> : null}
    </GovOriginContext.Provider>
  );
}
