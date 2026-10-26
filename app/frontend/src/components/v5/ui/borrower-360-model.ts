/** R14 U (K11): the Borrower 360 deep link, free of React (unit-tested). */

/** Borrower 360 holds the corporate book: CB ids (and the CG group ids it lists under them are not borrowers). */
import { edition } from "../../../lib/navigation.ts";

export function hasBorrower360(customerId: string | null | undefined): boolean {
  return /^CB\d{3,}$/i.test((customerId ?? "").trim());
}

/** The v5 Borrower 360 URL, as Early Warning's own link builds it (backend/ews_domain/drill.py): domain, customer_id and
 *  the period in the book's spelling ("2026Q2"); "Q2 2026" / "Q2-2026" are turned into it. */
export function b360Href(customerId: string, period?: string | null): string {
  // Deal Desk edition: Borrower 360 is not a screen; a borrower opens in Deal Desk's customer files (Round B makes the
  // deal's own Borrower 360 the target).
  if (edition() === "dealdesk") return `/deal-desk/customer-packs?cif=${encodeURIComponent((customerId ?? "").trim())}`;
  const q = new URLSearchParams({ domain: "corporate", customer_id: (customerId ?? "").trim() });
  const p = (period ?? "").trim();
  const m = /^(Q[1-4])[\s_-]?(\d{4})$/i.exec(p);
  const book = m ? `${m[2]}${m[1].toUpperCase()}` : /^\d{4}Q[1-4]$/i.test(p) ? p.toUpperCase() : "";
  if (book) q.set("period", book);
  return `/borrower-360?${q.toString()}`;
}

