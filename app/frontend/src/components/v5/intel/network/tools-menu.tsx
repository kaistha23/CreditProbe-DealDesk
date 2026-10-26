"use client";

/**
 * PLAN_R13 §I Session IC: the network tools for the Borrower 360 and What-If tools menus. A single "Network tools"
 * button (no first-screen clutter, per the mantra) opens a short menu; a pick opens its compact panel in a side sheet.
 *
 *   <NetworkToolsMenu module="b360" borrowerId={id} borrowerName={name} period={p} onOpenBorrower={open} />
 *   <NetworkToolsMenu module="whatif" />
 *
 * `NETWORK_TOOLS` is the menu as data, so another tools menu (M's shared one) can list the same entries.
 */

import * as React from "react";
import { Network, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Dropdown } from "@/components/v5/ui/dropdown"; // R14 U (K28)
import { useUrlPanel } from "@/components/v5/ui/url-state"; // R14 U (K1)

import { ContagionPanel } from "./contagion-panel";
import { EmployerPanel } from "./employer-panel";
import { EventTranslatorPanel } from "./event-panel";

export type NetworkToolId = "event" | "contagion" | "employer";
export type NetworkModule = "b360" | "whatif";

export interface NetworkTool {
  id: NetworkToolId; label: string; description: string; modules: NetworkModule[];
  /** The tool needs a borrower in context (Borrower 360 customer page). */
  needsBorrower: boolean; intent: string;
}

export const NETWORK_TOOLS: readonly NetworkTool[] = [
  { id: "event", label: "Event translator", description: "A shock this morning: who is hit, the ECL and Stage 2 hit, who to call",
    modules: ["b360", "whatif"], needsBorrower: false, intent: "intel.network.event" },
  { id: "contagion", label: "Contagion map", description: "If this borrower fails: who else is hit and by how much",
    modules: ["b360"], needsBorrower: true, intent: "intel.network.contagion" },
  { id: "employer", label: "Employer exposure", description: "Exposure to a project employer through the contractors it pays",
    modules: ["b360", "whatif"], needsBorrower: false, intent: "intel.network.employer" },
];

export function toolsFor(module: NetworkModule, hasBorrower: boolean): NetworkTool[] {
  return NETWORK_TOOLS.filter((t) => t.modules.includes(module) && (!t.needsBorrower || hasBorrower));
}

export function NetworkToolPanel({ tool, borrowerId, borrowerName, period, onOpenBorrower }: {
  tool: NetworkToolId; borrowerId?: string; borrowerName?: string; period?: string; onOpenBorrower?: (id: string) => void;
}) {
  if (tool === "event") return <EventTranslatorPanel borrowerName={borrowerName ?? borrowerId} period={period} onOpenBorrower={onOpenBorrower} />;
  if (tool === "contagion" && borrowerId) return <ContagionPanel borrowerId={borrowerId} period={period} onOpenBorrower={onOpenBorrower} />;
  if (tool === "employer") return <EmployerPanel employer={borrowerId ?? ""} period={period} onOpenBorrower={onOpenBorrower} />;
  return null;
}

export function NetworkToolsMenu({ module, borrowerId, borrowerName, period, onOpenBorrower, className }: {
  module: NetworkModule; borrowerId?: string; borrowerName?: string; period?: string;
  onOpenBorrower?: (id: string) => void; className?: string;
}) {
  // R14 U (K1): the open tool is in the address (?ntool=), so Back from a borrower opened inside it reopens it.
  const [raw, setRaw] = useUrlPanel("ntool");
  const open = (NETWORK_TOOLS.some((t) => t.id === raw) ? raw : null) as NetworkToolId | null;
  const setOpen = React.useCallback((v: NetworkToolId | null) => setRaw(v ?? ""), [setRaw]);
  const tools = toolsFor(module, Boolean(borrowerId));
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const go = (id: string) => { setOpen(null); onOpenBorrower?.(id); };
  return (
    <div className={cn("relative", className)} data-testid={`intel-network-tools-${module}`}>
      {/* R14 U (K28): the house dropdown */}
      <Dropdown label="Network tools" icon={<Network />} buttonTestId={`intel-network-tools-${module}-button`} menuTestId={`intel-network-tools-${module}-menu`}
                width={320} variant="ghost"
                sections={[{ items: tools.map((t) => ({ key: t.id, label: t.label, description: t.description, testId: `intel-network-tool-${t.id}`,
                                                       onSelect: () => setOpen(t.id) })) }]} />
      {open ? (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/20" onClick={() => setOpen(null)}>
          <aside role="dialog" aria-modal="true" aria-label={NETWORK_TOOLS.find((t) => t.id === open)?.label}
                 className="h-full w-[min(820px,100vw)] overflow-y-auto bg-surface-sunken p-4 shadow-xl"
                 onClick={(e) => e.stopPropagation()} data-testid={`intel-network-sheet-${open}`}>
            <div className="mb-2 flex justify-end">
              <Button variant="ghost" size="sm" onClick={() => setOpen(null)} aria-label="Close" data-testid="intel-network-sheet-close">
                <X size={14} aria-hidden />
              </Button>
            </div>
            <NetworkToolPanel tool={open} borrowerId={borrowerId} borrowerName={borrowerName} period={period}
                              onOpenBorrower={onOpenBorrower ? go : undefined} />
          </aside>
        </div>
      ) : null}
    </div>
  );
}
