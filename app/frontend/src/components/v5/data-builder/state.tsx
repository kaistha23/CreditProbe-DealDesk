/**
 * The Data Builder view lives in the address.
 *
 *   /data-builder?domain=cockpit&relation=corp_facility_quarter&period=2026Q2
 *     &compare=2026Q1&q=construction&f=[...]&cols=a,b&sort=ead_sar_mn&desc=1
 *     &page=2&size=50&tab=dictionary&view=compact
 *
 * Every change a reader makes is ONE history entry (density is replaced in
 * place), so Back walks back one step at a time and a copied link opens the
 * exact view.
 */
"use client";

import { useSearchParams } from "next/navigation";
import * as React from "react";

import type { Filter, Op } from "@/lib/v5/data-builder";

export const PAGE_SIZES = [25, 50, 100, 200, 500] as const;
/** PLAN_R10 S4: the selected dataset opens on its first 200 rows. */
export const DEFAULT_SIZE = 200;

export interface ViewState {
  domain: string;
  relation: string;
  period: string; // "" = the relation's latest period; "all" = every period
  compare: string;
  q: string;
  filters: Filter[];
  cols: string[];
  sort: string;
  desc: boolean;
  page: number; // 1-based
  size: number;
  tab: "rows" | "dictionary";
  view: "comfortable" | "compact";
}

const OPS: Op[] = ["eq", "neq", "gt", "gte", "lt", "lte", "in", "contains"];

function parseFilters(raw: string | null): Filter[] {
  if (!raw) return [];
  try {
    const data: unknown = JSON.parse(raw);
    if (!Array.isArray(data)) return [];
    return data
      .filter((f): f is Record<string, unknown> => typeof f === "object" && f !== null)
      .filter((f) => typeof f.column === "string" && OPS.includes(f.op as Op))
      .map((f) => ({ column: String(f.column), op: f.op as Op, value: f.value === undefined || f.value === null ? "" : String(f.value) }));
  } catch {
    return [];
  }
}

export function readState(query: URLSearchParams | { get(k: string): string | null }): ViewState {
  const size = Number(query.get("size"));
  const page = Number(query.get("page"));
  return {
    domain: query.get("domain") ?? "",
    relation: query.get("relation") ?? "",
    period: query.get("period") ?? "",
    compare: query.get("compare") ?? "",
    q: query.get("q") ?? "",
    filters: parseFilters(query.get("f")),
    cols: (query.get("cols") ?? "").split(",").map((c) => c.trim()).filter(Boolean),
    sort: query.get("sort") ?? "",
    desc: query.get("desc") === "1",
    page: Number.isFinite(page) && page >= 1 ? Math.floor(page) : 1,
    size: (PAGE_SIZES as readonly number[]).includes(size) ? size : DEFAULT_SIZE,
    tab: query.get("tab") === "dictionary" ? "dictionary" : "rows",
    view: query.get("view") === "compact" ? "compact" : "comfortable",
  };
}

export function toSearch(s: Partial<ViewState>): string {
  const p = new URLSearchParams();
  if (s.domain) p.set("domain", s.domain);
  if (s.relation) p.set("relation", s.relation);
  if (s.period) p.set("period", s.period);
  if (s.compare) p.set("compare", s.compare);
  if (s.q) p.set("q", s.q);
  if (s.filters?.length) p.set("f", JSON.stringify(s.filters));
  if (s.cols?.length) p.set("cols", s.cols.join(","));
  if (s.sort) p.set("sort", s.sort);
  if (s.sort && s.desc) p.set("desc", "1");
  if (s.page && s.page > 1) p.set("page", String(s.page));
  if (s.size && s.size !== DEFAULT_SIZE) p.set("size", String(s.size));
  if (s.tab === "dictionary") p.set("tab", "dictionary");
  if (s.view === "compact") p.set("view", "compact");
  const out = p.toString();
  return out ? `?${out}` : "";
}

export function hrefFor(s: Partial<ViewState>): string {
  return `/data-builder${toSearch(s)}`;
}

/** The view, and the two ways to change it: `push` (a Back step) and `replace` (none). */
export function useViewState() {
  const query = useSearchParams();
  const state = React.useMemo(() => readState(query), [query]);
  const write = React.useCallback((next: Partial<ViewState>, mode: "push" | "replace") => {
    const search = toSearch(next);
    if (search === (window.location.search || "")) return;
    const url = search || window.location.pathname;
    if (mode === "push") window.history.pushState(null, "", url);
    else window.history.replaceState(null, "", url);
  }, []);
  /** Change part of the view (one Back step). */
  const go = React.useCallback((patch: Partial<ViewState>) => write({ ...state, ...patch }, "push"), [state, write]);
  /** Open a fresh view (domain / relation), keeping only the density. */
  const open = React.useCallback((next: Partial<ViewState>) => write({ view: state.view, ...next }, "push"),
    [state.view, write]);
  const replace = React.useCallback((patch: Partial<ViewState>) => write({ ...state, ...patch }, "replace"),
    [state, write]);
  return { state, go, open, replace };
}

/** An anchor that navigates by pushState (no reload, one Back step) and still opens in a new tab. */
export function ViewLink({ to, className, children, testId, title, onNavigate }: {
  to: Partial<ViewState>; className?: string; children: React.ReactNode; testId?: string; title?: string;
  onNavigate?: () => void;
}) {
  const href = hrefFor(to);
  return (
    <a href={href} className={className} data-testid={testId} title={title}
       onClick={(e) => {
         if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
         e.preventDefault();
         onNavigate?.();
         if (href !== `${window.location.pathname}${window.location.search}`) window.history.pushState(null, "", href);
       }}>
      {children}
    </a>
  );
}
