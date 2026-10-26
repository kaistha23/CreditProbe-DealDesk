"use client";

/**
 * R16 t (M7): the thread actions on an answer that is a panel, not a chat turn (Early Warning level and customer,
 * Borrower 360, intel panels, agent runs). It reads the panel it sits in (the closest `container` element, else its
 * parent) as the reader sees it; `share` / `report` are off where the panel's own header already has them.
 */

import * as React from "react";

import { type ActionDoc, type ActionSource, type DomLike, type ModuleKey, composeDoc, domBlocks } from "@/lib/v5/thread-actions";

import { ThreadActionBar } from "./action-bar";

export function PanelActions({ module, id, title, question, sources = [], container, share = true, report = true, href, testId, className }: {
  module: ModuleKey; id: string; title: string; question?: string; sources?: ActionSource[];
  /** CSS selector of the panel to read (closest ancestor); default the parent element. */
  container?: string; share?: boolean; report?: boolean; href?: string; testId?: string; className?: string;
}) {
  const anchor = React.useRef<HTMLSpanElement | null>(null);
  const srcKey = JSON.stringify(sources);
  const panelEl = React.useCallback((): Element | null => {
    const a = anchor.current;
    return (container ? a?.closest(container) : a?.parentElement?.parentElement) ?? null;
  }, [container]);
  const getDoc = React.useCallback((): ActionDoc => {
    const el = panelEl();
    const path = href ?? (typeof window !== "undefined" ? `${window.location.pathname}${window.location.search}` : "/");
    return composeDoc(module, id, title, path, [{ question: question || title, answer_id: id, blocks: domBlocks(el as unknown as DomLike | null), sources }]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [module, id, title, question, panelEl, href, srcKey]);
  return (
    <span ref={anchor} className="contents">
      <ThreadActionBar module={module} threadId={id} getDoc={getDoc} share={share} report={report} question={question || title} getEl={panelEl} nearby
                       className={className ?? "border-t-0 pt-0"} testId={testId ?? `${module}-panel-actions`} />
    </span>
  );
}
