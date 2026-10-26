"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { modelDetailHref } from "@/ews-preview/lib/workspace/model-identity";

const CLASS = "text-text-secondary hover:text-accent";

/**
 * "Model details" in the preview header, carrying the book and period the
 * reader is currently on.
 *
 * A bare `/ews-preview/model` link silently reopened the default book: a
 * reader looking at Corporate clicked through and was shown the Retail rule
 * set with nothing on the screen saying so.
 */
export function ModelDetailsLink() {
  const params = useSearchParams();
  const domain = params.get("domain") === "corporate" ? "corporate" : "retail";
  return (
    <Link href={modelDetailHref(domain, params.get("period") ?? "")} className={CLASS} data-testid="ews-nav-model">
      Model details
    </Link>
  );
}

/**
 * The same link before the address is readable on the client. It opens the
 * page without a book, which the page then defaults, rather than holding the
 * whole header back for a search string.
 */
export function ModelDetailsLinkFallback() {
  return (
    <Link href="/early-warning/model" className={CLASS} data-testid="ews-nav-model">
      Model details
    </Link>
  );
}
