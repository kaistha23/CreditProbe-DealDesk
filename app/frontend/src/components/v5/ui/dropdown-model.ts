/**
 * R14 U (K28): the logic of the house dropdown, free of React so it is unit-tested with `node --test`.
 *
 * One dropdown for every menu in the product (deal More, Tools menus, Governance, the user / sign-out menu):
 * min width 260 px, one-line labels, 32 px rows, 16 px icons, section headers, muted descriptions, keyboard
 * navigation. This file holds the parts that have rules: which rows can take focus, where the arrow keys go,
 * how a count badge is explained.
 */

/** The fixed geometry of the house menu (also read by the component, so the test pins the numbers). */
export const DROPDOWN = {
  minWidth: 260,
  rowHeight: 32,
  iconSize: 16,
} as const;

export interface DropdownItemLike {
  key: string;
  disabled?: boolean;
  /** A row that renders its own content (a legacy button) still takes focus unless `focusable: false`. */
  focusable?: boolean;
}

export interface DropdownSectionLike<I extends DropdownItemLike = DropdownItemLike> {
  title?: string;
  items: I[];
}

/** Every row of every section, in order (sections with no items are dropped). */
export function flatten<I extends DropdownItemLike>(sections: DropdownSectionLike<I>[]): I[] {
  return sections.flatMap((s) => s.items);
}

/** Sections with at least one item: an empty section never shows its header. */
export function visibleSections<S extends DropdownSectionLike>(sections: S[]): S[] {
  return sections.filter((s) => s.items.length > 0);
}

function canFocus(i: DropdownItemLike): boolean {
  return !i.disabled && i.focusable !== false;
}

/**
 * Where focus goes on a key press. `current` is the index in the flattened list (-1: nothing focused yet).
 * ArrowDown / ArrowUp wrap; Home / End jump; disabled rows are skipped. Returns -1 when no row can take focus.
 * Any other key returns `current` unchanged (the component handles Enter / Escape / Tab itself).
 */
export function moveFocus(items: DropdownItemLike[], current: number, key: string): number {
  const n = items.length;
  const ok = items.map(canFocus);
  if (!ok.some(Boolean)) return -1;
  const first = ok.indexOf(true);
  const last = ok.lastIndexOf(true);
  switch (key) {
    case "Home": return first;
    case "End": return last;
    case "ArrowDown": {
      for (let step = 1; step <= n; step++) {
        const j = (((current < 0 ? -1 : current) + step) % n + n) % n;
        if (ok[j]) return j;
      }
      return first;
    }
    case "ArrowUp": {
      const start = current < 0 ? 0 : current;
      for (let step = 1; step <= n; step++) {
        const j = (((start - step) % n) + n) % n;
        if (ok[j]) return j;
      }
      return last;
    }
    default: return current;
  }
}

/**
 * Typeahead: the next focusable row whose label starts with the typed letter, after the current row (wrapping).
 */
export function typeahead(items: (DropdownItemLike & { label?: string })[], current: number, ch: string): number {
  const c = ch.toLowerCase();
  if (c.length !== 1 || !/[a-z0-9]/.test(c)) return current;
  const n = items.length;
  for (let step = 1; step <= n; step++) {
    const j = (((current < 0 ? -1 : current) + step) % n + n) % n;
    const it = items[j];
    if (canFocus(it) && (it.label ?? "").trim().toLowerCase().startsWith(c)) return j;
  }
  return current;
}

/**
 * The count on a menu button is never unexplained (K28): a badge always carries its words, or it is not shown.
 * `noun` is singular ("open item"); returns null for 0 / missing counts.
 */
export function badgeTooltip(count: number | null | undefined, noun: string): string | null {
  if (!count || count < 0 || !Number.isFinite(count)) return null;
  const n = Math.round(count);
  const plural = n === 1 ? noun : noun.endsWith("y") && !/[aeiou]y$/.test(noun) ? `${noun.slice(0, -1)}ies` : `${noun}s`;
  return `${n} ${plural}`;
}
