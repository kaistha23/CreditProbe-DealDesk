"use client";

/**
 * PLAN_R13 §I ID: the "Portfolio tools" menu for the Lenses and Deal Desk Book headers. One small button; each tool
 * opens its compact panel in a side drawer, so nothing new lands on the first screen (R13 mantra).
 */

import * as React from "react";
import { LineChart, X } from "lucide-react";

import { Dropdown } from "@/components/v5/ui/dropdown"; // R14 U (K28)
import { useUrlPanel } from "@/components/v5/ui/url-state"; // R14 U (K1)
import { type IntelMenu, intentsForMenu } from "@/lib/v5/intel-intents-id";

import { EclBridgePanel } from "./ecl-bridge-panel";
import { ExitsPanel } from "./exits-panel";
import { HeadroomPanel } from "./headroom-panel";
import { RwaPanel } from "./rwa-panel";
import { WorkoutPanel } from "./workout-panel";

export const PORTFOLIO_PANELS: Record<string, React.ComponentType> = {
  HeadroomPanel, ExitsPanel, RwaPanel, EclBridgePanel, WorkoutPanel,
};

/** The portfolio tools for a module menu: intent descriptor + panel component, in backlog order of the menu. */
export function portfolioTools(menu: IntelMenu) {
  return intentsForMenu(menu).filter((i) => i.session === "ID" && PORTFOLIO_PANELS[i.panel])
    .map((i) => ({ id: i.id, title: i.title, question: i.question, Panel: PORTFOLIO_PANELS[i.panel] }));
}

export function PortfolioDrawer({ title, question, onClose, children, testId }: {
  title: string; question: string; onClose: () => void; children: React.ReactNode; testId?: string;
}) {
  React.useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-[80] flex justify-end bg-black/20" onClick={onClose} data-testid={testId}>
      <aside role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}
             className="flex h-full w-full max-w-[820px] flex-col overflow-hidden border-l border-border bg-surface shadow-2xl">
        <header className="flex items-start gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Portfolio tools</p>
            <h2 className="truncate text-[15px] font-semibold text-text-primary">{title}</h2>
            <p className="text-[12px] text-text-secondary">{question}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 text-text-muted hover:bg-surface-hover"><X className="h-4 w-4" /></button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{children}</div>
      </aside>
    </div>
  );
}

/** R13 M: a tool from another session listed in the same menu (one Tools button per module header). */
export interface ExtraTool { key: string; title: string; question: string; onPick: () => void }

export function PortfolioToolsMenu({ menu, className, label = "Portfolio tools", extra = [] }: {
  menu: IntelMenu; className?: string; label?: string; extra?: ExtraTool[];
}) {
  const tools = portfolioTools(menu);
  const [tool, setTool] = useUrlPanel("tool"); // R14 U (K1): in the address, so Back reopens the drawer
  const active = tools.find((t) => t.id === tool);
  const close = React.useCallback(() => setTool(""), []);
  if (!tools.length && !extra.length) return null;
  // R14 U (K28): the house dropdown; extra tools (another session's) first, then the portfolio tools, each with its question.
  const sections = [
    { title: extra.length && tools.length ? "Book" : undefined,
      items: extra.map((t) => ({ key: t.key, label: t.title, description: t.question, testId: `portfolio-tool-${t.key}`, onSelect: t.onPick })) },
    { title: extra.length && tools.length ? "Portfolio" : undefined,
      items: tools.map((t) => ({ key: t.id, label: t.title, description: t.question, testId: `portfolio-tool-${t.id.split(".")[1]}`, onSelect: () => setTool(t.id) })) },
  ];
  return (
    <div className="relative" data-testid={`portfolio-tools-${menu}`}>
      <Dropdown label={label} icon={<LineChart />} buttonTestId={`portfolio-tools-${menu}-button`} menuTestId={`portfolio-tools-${menu}-menu`}
                width={340} buttonClassName={className} sections={sections} />
      {active ? (
        <PortfolioDrawer title={active.title} question={active.question} onClose={close} testId={`portfolio-drawer-${active.id.split(".")[1]}`}>
          <active.Panel />
        </PortfolioDrawer>) : null}
    </div>
  );
}
