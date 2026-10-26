"use client";

import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useCoreAuth } from "@/components/v5/core/auth";
import { AiPoweredMark } from "@/components/v5/core/ai-powered-mark";
import { QuantalphaLogo } from "@/components/v5/core/brand";

/** Only same-app paths are followed after sign-in. With none asked for, the Cockpit is the landing page (PLAN_R10 S1). */
export function safeNext(next: string | null): string {
  return next && /^\/(?!\/)/.test(next) && !next.startsWith("/login") ? next : "/";
}

/** Sign in with a username and password. The initial passwords are in ~/CreditProbe_Workspace/USERS_LOCAL.md. */
export function LoginForm() {
  const { signIn, status } = useCoreAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, next, router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password || busy) return;
    setBusy(true);
    setError(null);
    try {
      await signIn(username.trim(), password);
      router.replace(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That username or password is not right.");
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas px-6 py-12" data-testid="login-screen">
      <div className="w-full max-w-[340px]">
        <div className="mb-9 flex flex-col items-center text-center" data-testid="login-brand">
          <QuantalphaLogo height={44} className="text-text-primary" />
          <p className="mt-4 text-[13px] text-text-secondary">
            <span className="display font-semibold tracking-[0.01em] text-text-primary">CreditProbe<span className="ml-1 text-accent">AI</span></span>
            <span className="mx-1.5 text-text-muted">·</span>Credit Portfolio Intelligence
          </p>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label htmlFor="username" className="mb-1.5 block text-[11px] uppercase tracking-[0.08em] text-text-muted">Username</label>
            <input id="username" autoFocus autoComplete="username" value={username} data-testid="login-username"
                   onChange={(e) => setUsername(e.target.value)}
                   className="h-10 w-full rounded-md border border-border bg-surface px-3 text-sm text-text-primary focus:border-accent focus:outline-none" />
          </div>
          <div>
            <label htmlFor="password" className="mb-1.5 block text-[11px] uppercase tracking-[0.08em] text-text-muted">Password</label>
            <input id="password" type="password" autoComplete="current-password" value={password} data-testid="login-password"
                   onChange={(e) => setPassword(e.target.value)}
                   className="h-10 w-full rounded-md border border-border bg-surface px-3 text-sm text-text-primary focus:border-accent focus:outline-none" />
          </div>
          {error ? <p role="alert" data-testid="login-error" className="text-[13px] text-negative">{error}</p> : null}
          {status === "unreachable" ? (
            <p role="alert" className="text-[13px] text-negative">Sign-in is temporarily unavailable. Please try again in a moment.</p>
          ) : null}
          <Button type="submit" disabled={busy || !username.trim() || !password} className="w-full" data-testid="login-submit">
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
            Sign in
          </Button>
        </form>
        {/* R10 L1: the small chosen mark under Sign in, "AI powered" beneath; the R9 illustration is removed. */}
        <AiPoweredMark className="mt-8" />
      </div>
    </div>
  );
}
