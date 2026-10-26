"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { recordVisit } from "@/lib/v5/back-trail";

import { ErrorBoundary } from "@/components/system/error-boundary";
import { OriginBackLink } from "@/components/v5/ui/back-link"; // R14 U (K1): "← Back to <origin>" when the URL carries from=
import { AccessGuard } from "@/components/v5/admin/access-guard";
import { CoreAuthProvider, useCoreAuth } from "@/components/v5/core/auth";

import { ContentWidthProvider, useContentWidth } from "./content-width";
import { Header } from "./header";
import { NavProvider } from "./nav-state";
import { Sidebar } from "./sidebar";

/**
 * The application frame: header, sidebar, scrolling content area.
 *
 * Signing in is the Core service's (backend/workspace_v5): a session cookie, read
 * from `GET /api/v1/auth/me`. Nobody signed in is sent to /login and brought back
 * to the page they asked for. A page opened with `?embed=1` (a Mail attachment
 * opened in place) shows its content without the header and sidebar.
 *
 * The shell is the part that must never break, so the content area is wrapped in
 * its own error boundary. A failing page leaves the navigation usable instead of
 * blanking the window.
 *
 * The content column is capped at 1200px and generously padded. A page whose
 * content IS the width can ask for more with `useWideContent`, and the Cockpit
 * does. The horizontal padding is generous from `sm` up and modest below it.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <NavProvider>
      <ContentWidthProvider>
        <CoreAuthProvider>
          <React.Suspense fallback={<div className="min-h-dvh bg-canvas" aria-busy="true" />}>
            <Gate>{children}</Gate>
          </React.Suspense>
        </CoreAuthProvider>
      </ContentWidthProvider>
    </NavProvider>
  );
}

function Gate({ children }: { children: React.ReactNode }) {
  const { status } = useCoreAuth();
  const pathname = usePathname();
  const params = useSearchParams();
  const router = useRouter();
  const onLogin = pathname === "/login";
  const embed = params.get("embed") === "1";
  const query = params.toString();

  // R7: the trail Back reads where the browser has no Navigation API (lib/v5/back-trail.ts).
  React.useEffect(() => { recordVisit(pathname + (query ? `?${query}` : "")); }, [pathname, query]);

  React.useEffect(() => {
    if (status === "anonymous" && !onLogin) {
      const here = pathname + (query ? `?${query}` : "");
      router.replace(`/login?next=${encodeURIComponent(here)}`);
    }
  }, [status, onLogin, pathname, query, router]);

  if (onLogin) return <>{children}</>;
  // Still asking, or about to be sent to /login: a blank canvas is the honest state.
  if (status === "loading" || status === "anonymous") return <div className="min-h-dvh bg-canvas" aria-busy="true" />;
  if (status === "unreachable") {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-canvas px-6" role="alert" data-testid="core-unreachable">
        <p className="max-w-md text-center text-sm text-negative">
          Sign-in and Mail are temporarily unavailable. Please reload in a moment.
        </p>
      </div>
    );
  }
  if (embed) {
    return (
      <main className="min-h-dvh bg-canvas" data-embed="true">
        <ContentColumn>{children}</ContentColumn>
      </main>
    );
  }
  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <Header />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <ContentColumn><OriginBackLink /><AccessGuard>{children}</AccessGuard></ContentColumn>
        </main>
      </div>
    </div>
  );
}

function ContentColumn({ children }: { children: React.ReactNode }) {
  const { wide } = useContentWidth();
  return (
    <div
      data-testid="app-content-column"
      data-wide={wide ? "true" : "false"}
      className={
        "mx-auto px-4 py-8 sm:px-6 lg:px-9 " +
        (wide ? "max-w-[1600px]" : "max-w-[1200px]")
      }
    >
      <ErrorBoundary area="This page">{children}</ErrorBoundary>
    </div>
  );
}
