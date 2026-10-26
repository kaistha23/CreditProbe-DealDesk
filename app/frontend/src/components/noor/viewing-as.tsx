"use client";

/**
 * "Viewing as" (I17): for demo and admin accounts only, a switch in the top bar (RM / credit reviewer / CRO /
 * analyst) that re-renders the app as that role would see it. Normal users never see it, and their persona is always
 * their login's role.
 *
 * App-wide contract for other modules (Deal Desk's Prepare / Review views read this):
 *   - `useViewingAs()` -> { persona, chosen, allowed, setPersona }
 *   - `<html data-viewing-as="rm|reviewer|cro|analyst">` while a switch is set, and a `cp:viewing-as` window event
 *     (detail: { persona }) on every change.
 * The choice is kept per browser (localStorage `cp.viewingAs`), read with useSyncExternalStore so a change in another
 * tab is picked up and nothing renders twice on mount.
 */

import * as React from "react";
import { ChevronDown, Eye } from "lucide-react";

import { useDemoMode } from "@/components/system/demo-mode";
import { useCoreAuth } from "@/components/v5/core/auth";
import { cn } from "@/lib/utils";

import { PERSONAS, type Persona, canSwitch, effectivePersona, isPersona } from "./noor-model";

const KEY = "cp.viewingAs";
const EVENT = "cp:viewing-as";
const listeners = new Set<() => void>();

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  window.addEventListener("storage", fn);
  return () => { listeners.delete(fn); window.removeEventListener("storage", fn); };
}

function read(): Persona | null {
  try {
    const v = window.localStorage.getItem(KEY);
    return isPersona(v) ? v : null;
  } catch {
    return null;
  }
}

export function setViewingAs(p: Persona | null): void {
  try {
    if (p) window.localStorage.setItem(KEY, p);
    else window.localStorage.removeItem(KEY);
  } catch { /* private window: the switch lasts for this page only */ }
  listeners.forEach((fn) => fn());
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { persona: p } }));
}

export function useViewingAs(): { persona: Persona; chosen: Persona | null; allowed: boolean; setPersona: (p: Persona | null) => void } {
  const { user, effective } = useCoreAuth();
  const demo = useDemoMode();
  const chosen = React.useSyncExternalStore(subscribe, read, () => null);
  const allowed = canSwitch(user, demo.on);
  const persona = effectivePersona((effective ?? user)?.role, chosen, allowed);
  React.useEffect(() => {
    const el = document.documentElement;
    if (allowed && chosen) el.dataset.viewingAs = chosen;
    else delete el.dataset.viewingAs;
  }, [allowed, chosen]);
  return { persona, chosen: allowed ? chosen : null, allowed, setPersona: setViewingAs };
}

export function ViewingAsSwitch() {
  const { persona, chosen, allowed, setPersona } = useViewingAs();
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement | null>(null);
  React.useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);
  if (!allowed) return null;
  const label = PERSONAS.find((p) => p.id === persona)?.short ?? persona;
  return (
    <div ref={ref} className="relative" data-testid="viewing-as">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}
              title="Show the app as another role would see it (demo and administrator accounts only)"
              className={cn("flex h-8 items-center gap-1.5 rounded-md border px-2 text-[12px] transition-colors",
                chosen ? "border-accent/50 bg-accent-muted text-text-primary" : "border-border text-text-secondary hover:bg-surface-hover")}>
        <Eye className="size-3.5" aria-hidden />
        <span className="hidden lg:inline text-text-muted">Viewing as</span>
        <span className="font-medium" data-testid="viewing-as-current">{label}</span>
        <ChevronDown className="size-3" aria-hidden />
      </button>
      {open ? (
        <div role="menu" className="absolute right-0 top-9 z-50 w-56 rounded-md border border-border bg-surface-elevated p-1 shadow-lg">
          {PERSONAS.map((p) => (
            <button key={p.id} type="button" role="menuitemradio" aria-checked={persona === p.id}
                    data-testid={`viewing-as-${p.id}`}
                    onClick={() => { setPersona(p.id); setOpen(false); }}
                    className={cn("flex w-full flex-col items-start rounded px-2 py-1.5 text-left hover:bg-surface-hover",
                      persona === p.id && "bg-surface-selected")}>
              <span className="text-[12.5px] font-medium text-text-primary">{p.label}</span>
              <span className="text-[11px] text-text-muted">{p.brief}</span>
            </button>
          ))}
          {chosen ? (
            <button type="button" onClick={() => { setPersona(null); setOpen(false); }}
                    className="mt-1 w-full rounded border-t border-border px-2 py-1.5 text-left text-[11.5px] text-text-muted hover:bg-surface-hover">
              Back to my own role
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
