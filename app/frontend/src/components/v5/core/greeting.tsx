"use client";

import * as React from "react";
import { Pencil, X } from "lucide-react";

import { useCoreAuth } from "@/components/v5/core/auth";
import { core } from "@/lib/v5/core";

import { greetingName, salutationFor } from "./greeting-logic";

/**
 * The Cockpit greeting (PLAN_R6 B4): "Good morning, Anne".
 *
 * Time of day is the viewer's clock (read after hydration, so server and client
 * markup agree). The name is the signed-in user's first name, unless a
 * presenter has set a "Showing to" name (a client's name in a demo), which is
 * stored per user by the Core service and so survives sign-out and sign-in.
 * The pencil sets it; the cross clears it.
 */
export function CockpitGreeting({ fallbackName = "" }: { fallbackName?: string }) {
  const { user } = useCoreAuth();
  const [hour, setHour] = React.useState<number | null>(null);
  const [presenter, setPresenter] = React.useState("");
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState("");

  React.useEffect(() => {
    let live = true;
    // The clock is external state: read once on mount.
    const id = window.setTimeout(() => { if (live) setHour(new Date().getHours()); }, 0);
    core.preferences().then(
      (r) => { if (live) setPresenter(r.preferences.presenter_name ?? ""); },
      () => {},
    );
    return () => { live = false; window.clearTimeout(id); };
  }, []);

  const name = greetingName(presenter, user?.name ?? fallbackName);
  const salutation = hour === null ? "Good day" : salutationFor(hour);

  async function save(value: string) {
    setEditing(false);
    setPresenter(value.trim());
    try {
      const r = await core.setPreferences({ presenter_name: value.trim() });
      setPresenter(r.preferences.presenter_name ?? "");
    } catch {
      /* the greeting keeps the local value; the next load re-reads the server */
    }
  }

  return (
    <h1 className="text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl" data-testid="cockpit-v4-greeting">
      {salutation}
      {editing ? (
        <form
          className="ml-2 inline-flex items-center gap-2 align-middle"
          onSubmit={(e) => { e.preventDefault(); void save(draft); }}
        >
          <input
            autoFocus
            value={draft}
            maxLength={60}
            placeholder="Showing to…"
            aria-label="Showing to"
            data-testid="greeting-presenter-input"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") setEditing(false); }}
            className="h-9 w-56 rounded-md border border-border bg-surface px-2 text-base font-normal text-text-primary focus:border-accent focus:outline-none"
          />
          <button type="submit" className="text-sm font-medium text-accent">Save</button>
        </form>
      ) : (
        <>
          {name ? (
            <>
              ,{" "}
              <span className="font-normal italic" data-testid="cockpit-v4-greeting-name">{name}</span>
            </>
          ) : null}
          <button
            type="button"
            onClick={() => { setDraft(presenter); setEditing(true); }}
            title={presenter ? `Showing to ${presenter}. Change` : "Presenting? Set who you are showing this to"}
            aria-label="Set the Showing to name"
            data-testid="greeting-presenter-edit"
            className="ml-2 inline-flex size-7 items-center justify-center rounded-md align-middle text-text-muted opacity-60 transition hover:bg-surface-hover hover:text-text-primary hover:opacity-100"
          >
            <Pencil className="size-3.5" aria-hidden />
          </button>
          {presenter ? (
            <span className="ml-1 inline-flex items-center gap-1 align-middle text-xs font-normal text-text-muted" data-testid="greeting-presenter-chip">
              Showing to
              <button
                type="button"
                onClick={() => void save("")}
                aria-label="Clear the Showing to name"
                title="Clear: greet me by my own name"
                data-testid="greeting-presenter-clear"
                className="inline-flex size-5 items-center justify-center rounded hover:bg-surface-hover hover:text-text-primary"
              >
                <X className="size-3" aria-hidden />
              </button>
            </span>
          ) : null}
        </>
      )}
    </h1>
  );
}
