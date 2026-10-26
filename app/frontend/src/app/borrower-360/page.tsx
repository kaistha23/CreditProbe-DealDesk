import * as React from "react";

import { Borrower360Workspace } from "@/components/v5/b360/workspace";

/**
 * v5 Borrower 360 (module 2). Corporate borrowers and retail customers, read
 * from the v5 books, the Early Warning releases and the synthetic Bureau and
 * Open Banking domains by the Borrower 360 service (backend/b360, port 8502).
 * The view lives in the address (?domain=&customer_id=&period=&tab=; ?borrower=
 * is accepted as before), so the page is rendered per request and the part
 * that reads the address has a Suspense boundary of its own.
 */
export const dynamic = "force-dynamic";

export default function Borrower360Page() {
  return (
    <React.Suspense fallback={<p className="text-sm text-text-muted">Opening Borrower 360…</p>}>
      <Borrower360Workspace />
    </React.Suspense>
  );
}
