"use client";

/**
 * Round K: "Save this as a rule for your future documents?" — shown after an instruction edited a document.
 *
 * Self-contained: it asks the Deal Desk service what rule the instruction makes (`POST /rules/suggest`) and saves it
 * (`POST /rules`). CreditProbe does not ask when the instruction is about this deal's figures only, or when the analyst
 * (their team, the bank) already has the rule: it says so in one quiet line instead.
 *
 * Round W mounts it on the living document's hook with one line:
 *
 *   const [rulePrompt, onInstructionApplied] = useRulePrompt({ document: "proposal", source: { draft_id } });
 *   <LivingDocument onInstructionApplied={onInstructionApplied} />  {rulePrompt}
 */

import Link from "next/link";
import * as React from "react";
import { BookmarkPlus, Check, Loader2, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { type DocType, type Rule, type Scope, type SuggestResult, rules } from "@/lib/v5/dealdesk-rules";
import { friendlyMessage } from "@/lib/v5/errors";

export interface RulePromptProps {
  instruction: string;
  section?: string;
  sectionLabel?: string;
  document?: DocType;
  source?: Record<string, unknown>;
  onDone?: (saved: Rule | null) => void;
  className?: string;
}

const sel = "h-8 rounded-md border border-border bg-surface px-2 text-[12.5px] text-text-primary";

export function SaveAsRulePrompt({ instruction, section = "", sectionLabel = "", document = "both", source, onDone, className }: RulePromptProps) {
  const [s, setS] = React.useState<SuggestResult | null>(null);
  const [text, setText] = React.useState("");
  const [scope, setScope] = React.useState<Scope>("me");
  const [doc, setDoc] = React.useState<DocType>(document);
  const [onlySection, setOnlySection] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [saved, setSaved] = React.useState<{ rule: Rule; message: string } | null>(null);
  const [closed, setClosed] = React.useState(false);

  React.useEffect(() => {
    let live = true;
    setS(null); setSaved(null); setClosed(false); setError(null);
    rules.suggest({ instruction, section, section_label: sectionLabel, document }).then((r) => {
      if (!live) return;
      setS(r); setText(r.suggestion.text); setDoc(document);
      setOnlySection(!!section && ["wording", "avoid", "must_mention"].includes(r.suggestion.kind));
    }, (e) => live && setError(friendlyMessage(e)));
    return () => { live = false; };
  }, [instruction, section, sectionLabel, document]);

  async function save() {
    if (!s || busy || !text.trim()) return;
    setBusy(true); setError(null);
    try {
      const edited = text.trim() !== s.suggestion.text;
      const r = await rules.create({
        instruction, text: text.trim(), scope, document: doc, section: onlySection ? section : "", section_label: onlySection ? sectionLabel : "",
        ...(edited ? {} : { kind: s.suggestion.kind, params: s.suggestion.params }), source: { via: "instruction", ...(source ?? {}) },
      });
      setSaved(r); onDone?.(r.rule);
    } catch (e) { setError(friendlyMessage(e)); } finally { setBusy(false); }
  }

  if (closed) return null;
  if (error && !s) return null;  // the prompt never gets in the analyst's way
  if (!s) return null;
  if (saved) {
    return (
      <div className={cn("flex items-start gap-2 rounded-lg border border-positive/40 bg-positive-muted px-3 py-2 text-[12.5px]", className)}
           role="status" data-testid="rule-prompt-saved" data-rule={saved.rule.id}>
        <Check className="mt-0.5 size-4 shrink-0 text-positive" aria-hidden />
        <span className="text-text-primary">{saved.message} <Link href="/deal-desk/rules" className="text-accent hover:underline">My rules</Link></span>
      </div>
    );
  }
  if (!s.ask) {
    return s.why_not ? (
      <p className={cn("text-[11.5px] text-text-muted", className)} data-testid="rule-prompt-quiet">{s.why_not}</p>
    ) : null;
  }
  return (
    <div className={cn("space-y-2 rounded-lg border border-accent/30 bg-accent-muted/40 p-3", className)} data-testid="rule-prompt" data-kind={s.suggestion.kind}>
      <div className="flex items-start gap-2">
        <BookmarkPlus className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
        <p className="flex-1 text-[13px] font-semibold text-text-primary">{s.question}</p>
        <button type="button" aria-label="Not now" onClick={() => { setClosed(true); onDone?.(null); }} className="text-text-muted hover:text-text-primary"
                data-testid="rule-prompt-close"><X className="size-4" /></button>
      </div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={600} aria-label="The rule"
                className="w-full rounded-md border border-border bg-surface p-2 text-[12.5px] text-text-primary" data-testid="rule-prompt-text" />
      <p className="text-[11px] text-text-muted" data-testid="rule-prompt-kind">
        {s.suggestion.kind_label}{s.suggestion.deterministic ? ": CreditProbe applies it to every draft, with or without the model." : ": given to the model as an instruction each time it writes."}
      </p>
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <label className="flex items-center gap-1">For
          <select value={scope} onChange={(e) => setScope(e.target.value as Scope)} className={sel} data-testid="rule-prompt-scope">
            {s.scopes.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1">in
          <select value={doc} onChange={(e) => setDoc(e.target.value as DocType)} className={sel} data-testid="rule-prompt-document">
            {s.documents.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
          </select>
        </label>
        {section ? (
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={onlySection} onChange={(e) => setOnlySection(e.target.checked)} data-testid="rule-prompt-section" />
            only in {sectionLabel || section}
          </label>
        ) : null}
        <span className="ml-auto flex gap-2">
          <button type="button" onClick={() => { setClosed(true); onDone?.(null); }} className="rounded-md border border-border px-3 py-1 hover:bg-surface-hover"
                  data-testid="rule-prompt-no">Not now</button>
          <button type="button" onClick={() => void save()} disabled={busy || !text.trim()} data-testid="rule-prompt-yes"
                  className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1 font-medium text-accent-contrast disabled:opacity-60">
            {busy ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <Check className="size-3.5" aria-hidden />} Yes, save the rule
          </button>
        </span>
      </div>
      {error ? <p role="alert" className="text-[12px] text-negative">{error}</p> : null}
    </div>
  );
}

/** The one-line mount for Round W: returns the prompt element and the `onInstructionApplied(section, instruction)` handler. */
export function useRulePrompt(opts: { document?: DocType; source?: Record<string, unknown>; sectionLabel?: (section: string) => string } = {}):
  [React.ReactNode, (section: string, instruction: string) => void] {
  const [last, setLast] = React.useState<{ section: string; instruction: string; n: number } | null>(null);
  const on = React.useCallback((section: string, instruction: string) => {
    if (instruction && instruction.trim()) setLast((p) => ({ section, instruction: instruction.trim(), n: (p?.n ?? 0) + 1 }));
  }, []);
  const el = last ? (
    <SaveAsRulePrompt key={last.n} instruction={last.instruction} section={last.section} sectionLabel={opts.sectionLabel?.(last.section) ?? last.section}
                      document={opts.document} source={opts.source} onDone={() => undefined} />
  ) : null;
  return [el, on];
}

/** Round W's `registerAfterInstruction` adapter (paperws/hooks.ts AfterInstructionProps): after the merge, one line in an index
 *  file: `registerAfterInstruction(AfterInstructionRulePrompt);` */
export function AfterInstructionRulePrompt(p: {
  section: { key: string; heading: string }; instruction: string; kind: "proposal" | "request"; wsId: string; proposalId: string;
  version: number; onDone: () => void;
}) {
  return (
    <SaveAsRulePrompt instruction={p.instruction} section={p.section.key} sectionLabel={p.section.heading} document={p.kind}
                      source={{ via: "paper-workspace", ws_id: p.wsId, proposal_id: p.proposalId, version: p.version }} onDone={() => p.onDone()} />
  );
}
