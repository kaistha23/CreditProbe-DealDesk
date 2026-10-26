"use client";

/**
 * R14 U (K28): the one house dropdown for every menu in the product.
 *
 *   <Dropdown label="More" icon={<MoreHorizontal />} badge={{ count: 8, noun: "open item" }}
 *             sections={[{ title: "Deal file", items: [...] }, { title: "Intelligence", items: [...] }]} />
 *
 * Geometry is fixed (dropdown-model.ts → DROPDOWN): min width 260 px, labels on one line (truncated, never wrapped),
 * 32 px rows, 16 px icons in a fixed column, section headers in small caps, an optional muted description under a
 * label, shadow and radius from the house kit. Keyboard: Enter / Space / ArrowDown on the button opens it; ArrowUp /
 * ArrowDown / Home / End move; a letter jumps to the next row starting with it; Enter / Space picks; Escape closes and
 * returns focus to the button; Tab closes. A click outside closes.
 *
 * Stable API (sessions g, i, f, p consume it): `Dropdown`, `DropdownItem`, `DropdownSection`. Add props, never
 * rename them. Test ids: `testId` on the wrapper, `${testId}-button` on the button unless `buttonTestId` is given,
 * `${testId}-menu` on the menu unless `menuTestId` is given, and each item's own `testId`.
 */

import Link from "next/link";
import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

import { DROPDOWN, badgeTooltip, flatten, moveFocus, typeahead, visibleSections } from "./dropdown-model";

export interface DropdownItem {
  key: string;
  label: string;
  /** One short muted line under the label (kept to one line). */
  description?: string;
  /** A lucide icon element; sized to 16 px by the menu. */
  icon?: React.ReactNode;
  /** Picks the row (the menu closes first). */
  onSelect?: () => void;
  /** Or navigates (a Next link). */
  href?: string;
  disabled?: boolean;
  /** Why the row is disabled (shown as its tooltip and description). */
  disabledReason?: string;
  /** Accent the row (the step's primary action). */
  emphasis?: boolean;
  /** Danger styling (Sign out is not danger; Delete would be). */
  danger?: boolean;
  /** A count on the row, always with its words. */
  badge?: { count: number | null | undefined; noun: string };
  /** Escape hatch: render a legacy control as the row's body (it keeps the row's height and padding). */
  render?: (close: () => void) => React.ReactNode;
  testId?: string;
}

export interface DropdownSection {
  title?: string;
  items: DropdownItem[];
}

export interface DropdownProps {
  /** The button's words (optional only with renderTrigger). */
  label?: React.ReactNode;
  icon?: React.ReactNode;
  sections: DropdownSection[];
  /** A count on the button. Shown only with its tooltip ("8 open items"); null/0 hides it. */
  badge?: { count: number | null | undefined; noun: string };
  /** Content above the first section (the user menu's name and role block). */
  header?: React.ReactNode;
  /** Content below the last section. */
  footer?: React.ReactNode;
  align?: "start" | "end";
  /** Menu width in px; never below 260. */
  width?: number;
  /** "outline" (default: bordered header button), "ghost" (borderless), or a fully custom trigger. */
  variant?: "outline" | "ghost";
  renderTrigger?: (p: { open: boolean; toggle: () => void; ref: React.Ref<HTMLButtonElement>; props: React.ButtonHTMLAttributes<HTMLButtonElement> }) => React.ReactNode;
  ariaLabel?: string;
  testId?: string;
  buttonTestId?: string;
  menuTestId?: string;
  className?: string;
  buttonClassName?: string;
  /** Controlled open state (optional). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Extra attributes on the wrapper (data-view etc.). */
  wrapperProps?: React.HTMLAttributes<HTMLDivElement> & Record<`data-${string}`, string | undefined>;
}

export function Dropdown({
  label, icon, sections, badge, header, footer, align = "end", width, variant = "outline", renderTrigger, ariaLabel,
  testId, buttonTestId, menuTestId, className, buttonClassName, open: controlled, onOpenChange, wrapperProps,
}: DropdownProps) {
  const [inner, setInner] = React.useState(false);
  const open = controlled ?? inner;
  const setOpen = React.useCallback((v: boolean) => { if (controlled === undefined) setInner(v); onOpenChange?.(v); }, [controlled, onOpenChange]);
  const [active, setActive] = React.useState(-1);
  const box = React.useRef<HTMLDivElement | null>(null);
  const menu = React.useRef<HTMLDivElement | null>(null);
  const trigger = React.useRef<HTMLButtonElement | null>(null);
  const rows = React.useRef<(HTMLElement | null)[]>([]);
  const menuId = React.useId();

  const shown = visibleSections(sections);
  const flat = flatten(shown);
  // The icon column is kept only when some row has an icon (a text-only menu is not indented).
  const anyIcon = flat.some((x) => x.icon);

  const close = React.useCallback((focusButton = false) => {
    setOpen(false);
    setActive(-1);
    if (focusButton) window.setTimeout(() => trigger.current?.focus(), 0);
  }, [setOpen]);

  React.useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) close(); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open, close]);

  // Focus follows the active row; with none active the menu itself holds focus (so the keys work).
  React.useEffect(() => {
    if (!open) return;
    const el = active >= 0 ? rows.current[active] : menu.current;
    el?.focus({ preventScroll: active < 0 });
  }, [open, active]);

  const pick = (it: DropdownItem) => {
    if (it.disabled) return;
    close();
    it.onSelect?.();
  };

  const onMenuKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(true); return; }
    if (e.key === "Tab") { close(); return; }
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
      e.preventDefault();
      setActive((a) => moveFocus(flat, a, e.key));
      return;
    }
    if ((e.key === "Enter" || e.key === " ") && active >= 0) {
      const it = flat[active];
      if (it && !it.render && !it.href) { e.preventDefault(); pick(it); }
      return;
    }
    if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) {
      setActive((a) => typeahead(flat, a, e.key));
    }
  };

  const onButtonKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      setActive(moveFocus(flat, -1, e.key === "ArrowDown" ? "Home" : "End"));
    }
  };

  const tip = badge ? badgeTooltip(badge.count, badge.noun) : null;
  const toggle = () => { if (open) close(); else { setActive(-1); setOpen(true); } };
  const triggerProps: React.ButtonHTMLAttributes<HTMLButtonElement> & Record<string, unknown> = {
    type: "button", onClick: toggle, onKeyDown: onButtonKey, "aria-haspopup": "menu", "aria-expanded": open,
    "aria-controls": open ? menuId : undefined, "aria-label": ariaLabel,
    "data-testid": buttonTestId ?? (testId ? `${testId}-button` : undefined),
  };

  let i = -1;
  return (
    <div ref={box} className={cn("relative shrink-0", className)} data-testid={testId} {...wrapperProps}>
      {renderTrigger ? renderTrigger({ open, toggle, ref: trigger, props: triggerProps }) : (
        <button ref={trigger} {...triggerProps}
                className={cn("inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-md px-3 text-[13px] text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary",
                              variant === "outline" && "border border-border bg-surface", open && "bg-surface-hover text-text-primary", buttonClassName)}>
          {icon ? <span className="inline-flex size-4 items-center justify-center [&>svg]:size-[15px]" aria-hidden>{icon}</span> : null}
          <span>{label}</span>
          {tip ? (
            <span title={tip} aria-label={tip} data-testid={testId ? `${testId}-badge` : undefined}
                  className="ml-0.5 rounded-full bg-warning/15 px-1.5 text-[11px] font-medium leading-4 text-warning">{Math.round(badge!.count as number)}</span>
          ) : null}
          <ChevronDown size={13} aria-hidden className={cn("text-text-muted", open && "rotate-180")} />
        </button>
      )}
      {open ? (
        <div ref={menu} id={menuId} role="menu" tabIndex={-1} aria-label={ariaLabel ?? (typeof label === "string" ? label : undefined)}
             onKeyDown={onMenuKey} data-testid={menuTestId ?? (testId ? `${testId}-menu` : undefined)} data-house-dropdown="1"
             style={{ minWidth: DROPDOWN.minWidth, width: width ? Math.max(width, DROPDOWN.minWidth) : undefined }}
             className={cn("absolute top-full z-50 mt-1 max-h-[min(70vh,560px)] overflow-y-auto rounded-lg border border-border bg-surface p-1 shadow-overlay outline-none",
                           align === "end" ? "right-0" : "left-0")}>
          {header ? <div className="border-b border-border px-2.5 pb-2 pt-1.5" data-dropdown-header="1">{header}</div> : null}
          {shown.map((s, si) => (
            <div key={s.title ?? `s${si}`} role="group" aria-label={s.title}
                 className={cn(si > 0 && "mt-1 border-t border-border pt-1", header && si === 0 && "mt-1")}>
              {s.title ? (
                <div className="px-2.5 pb-0.5 pt-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted" data-dropdown-section={s.title}>{s.title}</div>
              ) : null}
              {s.items.map((it) => {
                i += 1;
                const idx = i;
                const rowTip = it.badge ? badgeTooltip(it.badge.count, it.badge.noun) : null;
                const body = (
                  <>
                    {anyIcon ? <span className="flex size-4 shrink-0 items-center justify-center text-text-muted [&>svg]:size-4" aria-hidden>{it.icon ?? null}</span> : null}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate leading-5">{it.label}</span>
                      {it.description || (it.disabled && it.disabledReason) ? (
                        <span className="line-clamp-2 block text-[11.5px] leading-4 text-text-muted">{it.disabled && it.disabledReason ? it.disabledReason : it.description}</span>
                      ) : null}
                    </span>
                    {rowTip ? <span title={rowTip} aria-label={rowTip} className="shrink-0 rounded-full bg-warning/15 px-1.5 text-[11px] font-medium leading-4 text-warning">{Math.round(it.badge!.count as number)}</span> : null}
                  </>
                );
                const cls = cn("flex w-full items-center gap-2.5 rounded-md px-2.5 text-left text-[13px] outline-none transition-colors focus-visible:outline-none focus-visible:ring-0",
                               it.description || (it.disabled && it.disabledReason) ? "min-h-[40px] py-1.5" : "h-8",
                               it.disabled ? "cursor-not-allowed text-text-muted" : "hover:bg-surface-hover focus:bg-surface-hover",
                               it.emphasis ? "font-medium text-accent" : it.danger ? "text-negative" : !it.disabled && "text-text-primary",
                               active === idx && "bg-surface-hover");
                const common = {
                  role: "menuitem", tabIndex: -1, "data-testid": it.testId, "aria-disabled": it.disabled || undefined,
                  title: it.disabled ? it.disabledReason : it.description,
                  onMouseEnter: () => { if (!it.disabled) setActive(idx); },
                  ref: (el: HTMLElement | null) => { rows.current[idx] = el; },
                } as const;
                if (it.render) {
                  return (
                    <div key={it.key} {...common} className={cn(cls, "h-auto min-h-8 px-1.5 py-0.5")}>{it.render(() => close())}</div>
                  );
                }
                if (it.href && !it.disabled) {
                  return (
                    <Link key={it.key} href={it.href} {...common} onClick={() => { close(); it.onSelect?.(); }} className={cls}>{body}</Link>
                  );
                }
                return (
                  <button key={it.key} type="button" {...common} disabled={it.disabled} onClick={() => pick(it)} className={cls}>{body}</button>
                );
              })}
            </div>
          ))}
          {footer ? <div className="mt-1 border-t border-border px-2.5 pb-1 pt-2">{footer}</div> : null}
        </div>
      ) : null}
    </div>
  );
}
