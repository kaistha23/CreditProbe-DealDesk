"use client";

/**
 * R14 U (K1): a drawer or tool that lives in the address, so "← Back to <origin>" (and the browser's Back) return to
 * the page with the same drawer open. Replace, not push: opening a drawer is not a step of its own.
 *
 *   const [tool, setTool] = useUrlPanel("tool");   // ?tool=calls
 */

import { useSearchParams } from "next/navigation";
import * as React from "react";

export function useUrlPanel(key: string): [string, (value: string) => void] {
  const params = useSearchParams();
  const value = params.get(key) ?? "";
  const set = React.useCallback((next: string) => {
    try {
      const u = new URL(window.location.href);
      if (next) u.searchParams.set(key, next); else u.searchParams.delete(key);
      // null, not history.state: Next copies its own state and then updates useSearchParams (with its state passed
      // through, it treats the call as its own and the hook would not see the change).
      window.history.replaceState(null, "", u.toString());
    } catch { /* the drawer still opens or closes from the caller's own render */ }
  }, [key]);
  return [value, set];
}
