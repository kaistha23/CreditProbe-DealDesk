"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";

import { ModelPanel, type EwsSurface } from "@/ews-preview/components/guided/ews-drill";
import { DomainSwitchPlain } from "@/ews-preview/components/guided/domain-toggle";
import { modelMeta, type ModelMeta } from "@/ews-preview/lib/workspace/canonical";
import { modelDisplayState, modelIdentity } from "@/ews-preview/lib/workspace/model-identity";
import type { DomainId } from "@/ews-preview/lib/workspace/objects";

/**
 * The rule set on its own page: what it reads, which rules this release can
 * evaluate, what they tripped, the catalogue's own input coverage and the
 * reference model's compatibility statement. Provenance and method live here,
 * so the portfolio screen stays a business screen.
 *
 * The book-and-period identity is computed by `modelIdentity` and handed to
 * the panel unchanged. It is not a sentence for a reader: the panel uses it to
 * decide whether the reading it holds belongs to the book on screen, and a
 * sentence makes that test fail for ever.
 */
export function EwsModelDetails() {
  const params = useSearchParams();
  const fromAddress: DomainId = params.get("domain") === "corporate" ? "corporate" : "retail";
  const [domain, setDomain] = React.useState<DomainId>(fromAddress);
  const period = params.get("period") ?? "";
  const [surface, setSurface] = React.useState<EwsSurface>("model");
  const [model, setModel] = React.useState<ModelMeta | null>(null);
  const [error, setError] = React.useState("");
  // Asking again after a failure, without making the reader re-navigate.
  const [attempt, setAttempt] = React.useState(0);

  const identity = modelIdentity(domain, period);

  React.useEffect(() => {
    let live = true;
    // A new book or a new period is a new question: the previous answer AND
    // the previous failure both stop applying the moment it is asked. Leaving
    // the error up left a page that had recovered still reading as broken,
    // with no way back other than a reload.
    setModel(null);
    setError("");
    modelMeta({ domain, period })
      .then((m) => {
        if (live) setModel(m);
      })
      .catch((e: unknown) => {
        if (live) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      live = false;
    };
  }, [domain, period, attempt]);

  const state = modelDisplayState({ model, identity, error });

  return (
    <div className="space-y-4" data-testid="ews-model-page" data-state={state}>
      {/* The heading and the book switch stay up in every state. On a failure
          they are the way out: switching book asks again for the other book,
          which is how a reader recovers from one book's read failing. */}
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold text-text-primary">Model details</h1>
        <DomainSwitchPlain value={domain} onChange={setDomain} />
        {period ? (
          <span className="font-mono text-xs text-text-muted" data-testid="ews-model-period">
            {period}
          </span>
        ) : null}
      </header>
      {state === "error" ? (
        <div
          role="alert"
          className="space-y-2 rounded-md border border-negative bg-negative-muted px-3 py-2 text-sm text-negative"
          data-testid="ews-model-error"
        >
          <p>
            The model details for the {domain} book
            {period ? ` at ${period}` : ""} could not be read: {error}
          </p>
          <button
            type="button"
            onClick={() => setAttempt((n) => n + 1)}
            className="rounded-md border border-negative px-2.5 py-1 text-xs"
            data-testid="ews-model-retry"
          >
            Try reading it again
          </button>
        </div>
      ) : null}
      {state === "loading" ? (
        <p className="text-sm text-text-muted" data-testid="ews-model-loading">
          Reading the {domain} rule set{period ? ` for ${period}` : ""}…
        </p>
      ) : null}
      {state === "ready" ? (
        <ModelPanel
          model={model}
          identity={identity}
          surface={surface}
          onSurface={setSurface}
          ownerNoun={model?.owner_grain === "borrower" ? "borrowers" : "customers"}
        />
      ) : null}
    </div>
  );
}
