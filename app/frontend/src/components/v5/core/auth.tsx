"use client";

import * as React from "react";

import { CoreError, core, type Me, type User } from "@/lib/v5/core";

/**
 * Who is signed in (v5 Core service). One session read on load, shared by everything.
 *
 * `status` separates "still asking" from "nobody is signed in" so a signed-in
 * reader is never flashed a login page. `user` is who signed in; `effective` is
 * who the data is shown for, which differs only while the Administrator is
 * viewing as someone else.
 */
export type CoreAuthStatus = "loading" | "anonymous" | "authenticated" | "unreachable";

interface State {
  status: CoreAuthStatus;
  me: Me | null;
  user: User | null;
  effective: User | null;
  viewingAs: User | null;
  isAdmin: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  viewAs: (username: string | null) => Promise<void>;
  refresh: () => Promise<void>;
}

const Ctx = React.createContext<State>({
  status: "loading", me: null, user: null, effective: null, viewingAs: null, isAdmin: false,
  signIn: async () => { throw new Error("No CoreAuthProvider"); }, signOut: async () => {},
  viewAs: async () => {}, refresh: async () => {},
});

export function CoreAuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = React.useState<CoreAuthStatus>("loading");
  const [me, setMe] = React.useState<Me | null>(null);
  const [nonce, setNonce] = React.useState(0);

  // The session is read once on load and again whenever refresh() is called; state lands in promise callbacks.
  React.useEffect(() => {
    let live = true;
    core.session().then(
      (m) => {
        if (!live) return;
        if (!m.authenticated) { setMe(null); setStatus("anonymous"); return; }
        setMe(m);
        setStatus("authenticated");
      },
      (e: unknown) => {
        if (!live) return;
        setMe(null);
        setStatus(e instanceof CoreError && e.status === 401 ? "anonymous" : "unreachable");
      },
    );
    return () => { live = false; };
  }, [nonce]);

  const refresh = React.useCallback(async () => { setNonce((n) => n + 1); }, []);
  const value = React.useMemo<State>(() => ({
    status, me, user: me?.user ?? null, effective: me?.effective_user ?? null, viewingAs: me?.viewing_as ?? null,
    isAdmin: me?.is_admin ?? false,
    signIn: async (username, password) => { setMe(await core.login(username, password)); setStatus("authenticated"); },
    signOut: async () => { try { await core.logout(); } finally { setMe(null); setStatus("anonymous"); } },
    viewAs: async (username) => { setMe(await core.viewAs(username)); },
    refresh,
  }), [status, me, refresh]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCoreAuth(): State {
  return React.useContext(Ctx);
}
