"use client";

/**
 * Round K: the analyst's rules page (Deal Desk → My rules, also from the account menu): every rule that shapes the documents
 * they write — their own, their team's, the bank's — editable where they may, and a place to try "Save this as a rule?".
 */

import * as React from "react";

import { PageTop } from "@/components/v5/workspace/parts";
import { SaveAsRulePrompt } from "./save-rule-prompt";
import { RulesList } from "./rules-list";

export function MyRulesPage() {
  const [draft, setDraft] = React.useState("");
  const [tried, setTried] = React.useState<{ text: string; n: number } | null>(null);
  const [tick, setTick] = React.useState(0);
  return (
    <div className="space-y-6" data-testid="my-rules">
      <PageTop eyebrow="Deal Desk" title="My rules"
               about="Your writing rules, your team's and the bank's. CreditProbe applies them to every credit request and proposal you write, and lists them under “Rules applied” on the document." />
      <section className="space-y-2 rounded-lg border border-border bg-surface p-4" data-testid="my-rules-try">
        <h2 className="text-[14px] font-semibold text-text-primary">An instruction you gave in a document</h2>
        <p className="text-[12.5px] text-text-secondary">When you tell CreditProbe to change a document, it asks whether to keep the instruction as a rule. Type one to see.</p>
        <div className="flex gap-2">
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="For example: say obligor, not borrower"
                 className="h-9 flex-1 rounded-md border border-border bg-surface px-2 text-[13px]" data-testid="my-rules-try-input" aria-label="Instruction" />
          <button type="button" disabled={!draft.trim()} onClick={() => setTried((t) => ({ text: draft.trim(), n: (t?.n ?? 0) + 1 }))}
                  className="rounded-md border border-border px-3 text-[12.5px] hover:bg-surface-hover disabled:opacity-50" data-testid="my-rules-try-go">Apply</button>
        </div>
        {tried ? <SaveAsRulePrompt key={tried.n} instruction={tried.text} document="both" source={{ via: "my-rules" }} onDone={() => setTick((n) => n + 1)} /> : null}
      </section>
      <RulesList key={tick} title="Rules in force for you" testId="my-rules-list" />
    </div>
  );
}
