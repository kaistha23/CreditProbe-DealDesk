/**
 * The Borrower 360 book list's state, in the address (PLAN_R4 B2).
 *
 * Search, filters, sort, page and page size live in the URL next to the
 * customer keys (domain, customer_id, period, tab), so a row opened from the
 * list and Back (the browser's or the screen's) return to the same list on the
 * same page. Pure functions only: no React, no network (unit-tested).
 */

export const FILTER_KEYS = [
  "segment", "subsegment", "region", "branch", "product", "band", "stage", "ews", "dpd", "ead_min", "ead_max",
  // PLAN_R9 B1/B2: a top card, SICR reason, UTP reason, watch status, relationship manager.
  "card", "sicr", "utp", "watch", "rm",
] as const;
export type FilterKey = (typeof FILTER_KEYS)[number];

export const LIST_KEYS = ["q", ...FILTER_KEYS, "sort", "dir", "page", "size"] as const;
export type ListKey = (typeof LIST_KEYS)[number];

export const PAGE_SIZES = [25, 50, 100] as const;
export const DEFAULT_SIZE = 50;

export interface ListState {
  q: string;
  filters: Record<FilterKey, string>;
  sort: string;
  dir: "" | "asc" | "desc";
  page: number;
  size: number;
}

interface ParamsLike { get(name: string): string | null }

export function emptyFilters(): Record<FilterKey, string> {
  return Object.fromEntries(FILTER_KEYS.map((k) => [k, ""])) as Record<FilterKey, string>;
}

export function readList(params: ParamsLike): ListState {
  const filters = emptyFilters();
  for (const k of FILTER_KEYS) filters[k] = (params.get(k) ?? "").trim();
  const dir = params.get("dir");
  const page = Number(params.get("page") ?? "1");
  const size = Number(params.get("size") ?? DEFAULT_SIZE);
  return {
    q: (params.get("q") ?? "").trim(),
    filters,
    sort: (params.get("sort") ?? "").trim(),
    dir: dir === "asc" || dir === "desc" ? dir : "",
    page: Number.isInteger(page) && page >= 1 ? page : 1,
    size: (PAGE_SIZES as readonly number[]).includes(size) ? size : DEFAULT_SIZE,
  };
}

/** The list keys as URL entries, defaults left out (page 1, size 50, no sort, empty filters). */
export function listEntries(s: ListState): [ListKey, string][] {
  const out: [ListKey, string][] = [];
  if (s.q) out.push(["q", s.q]);
  for (const k of FILTER_KEYS) if (s.filters[k]) out.push([k, s.filters[k]]);
  if (s.sort) out.push(["sort", s.sort]);
  if (s.sort && s.dir) out.push(["dir", s.dir]);
  if (s.page > 1) out.push(["page", String(s.page)]);
  if (s.size !== DEFAULT_SIZE) out.push(["size", String(s.size)]);
  return out;
}

/** The query the service's /list and /list/export.xlsx take. */
export function apiQuery(s: ListState): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  if (s.q) out.q = s.q;
  for (const k of FILTER_KEYS) if (s.filters[k]) out[k] = s.filters[k];
  if (s.sort) out.sort = s.sort;
  if (s.sort && s.dir) out.dir = s.dir;
  out.offset = (s.page - 1) * s.size;
  out.limit = s.size;
  return out;
}

/** A filter changed: the page goes back to one; a new sector clears a sub-sector that is not in it. */
export function withFilter(s: ListState, key: FilterKey, value: string, subParent?: (sub: string) => string | undefined): ListState {
  const filters = { ...s.filters, [key]: value };
  if (key === "segment" && filters.subsegment && subParent && value && subParent(filters.subsegment) !== value) {
    filters.subsegment = "";
  }
  return { ...s, filters, page: 1 };
}

/** Click on a column header: a new column sorts ascending for text, descending for figures; again flips it. */
export function nextSort(s: ListState, key: string, numeric: boolean, defaultSort: { sort: string; dir: string }): ListState {
  const current = s.sort || defaultSort.sort;
  const currentDir = s.sort ? (s.dir || "asc") : defaultSort.dir;
  const dir: "asc" | "desc" = current === key ? (currentDir === "asc" ? "desc" : "asc") : numeric ? "desc" : "asc";
  return { ...s, sort: key, dir, page: 1 };
}

export function pageCount(total: number, size: number): number {
  return Math.max(1, Math.ceil(total / size));
}

export function activeFilterCount(s: ListState): number {
  return FILTER_KEYS.filter((k) => s.filters[k]).length + (s.q ? 1 : 0);
}

// ------------------------------------------------------------- the column chooser

export function columnsStorageKey(user: string | null | undefined, domain: string): string {
  return `cp.b360.list.columns.${user || "anonymous"}.${domain}`;
}

/**
 * The columns to show: the stored choice (known keys only, in the service's order), else the defaults.
 * The id column is always shown.
 */
export function visibleColumns(all: { key: string; default: boolean }[], stored: string | null): string[] {
  let chosen: string[] | null = null;
  if (stored) {
    try {
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed)) chosen = parsed.filter((x): x is string => typeof x === "string");
    } catch {
      chosen = null;
    }
  }
  const keys = all.map((c) => c.key);
  const pick = chosen && chosen.some((k) => keys.includes(k)) ? new Set(chosen) : new Set(all.filter((c) => c.default).map((c) => c.key));
  pick.add("id");
  return keys.filter((k) => pick.has(k));
}
