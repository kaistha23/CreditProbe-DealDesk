import * as React from "react";

import { LensesHome } from "@/components/v5/lenses/home";

/**
 * v5 Lenses (PLAN_R5 Session L): ask for a dashboard and a lens opens; saved lenses, shared lenses and templates below.
 * Served by the Lenses service (port 8509). ?book=retail switches the book.
 */
export const dynamic = "force-dynamic";

export default function LensesPage() {
  return (
    <React.Suspense fallback={<p className="text-sm text-text-muted">Opening Lenses…</p>}>
      <LensesHome />
    </React.Suspense>
  );
}
