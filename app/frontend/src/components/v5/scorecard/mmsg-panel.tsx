"use client";

/**
 * R16 M8: under a validation, the MMSG validation report (Word) and the maker-checker conclusion. The rules propose a
 * conclusion (fit / fit with conditions / not fit) with their reasons; a maker records the conclusion; a checker other
 * than the maker (Risk, Model Validation or the Administrator) approves or returns it. Only an approved conclusion
 * counts as the independent validation on the monitoring front page.
 */

import * as React from "react";
import { FileText } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { friendlyMessage } from "@/lib/v5/errors";
import { useLoad } from "@/lib/v5/scorecard";
import { type ConclusionId, type ConclusionView, mmsgHref, monitor } from "@/lib/v5/scorecard-monitor";

import { day } from "./monitor-model";

export const CONCLUSION_EVENT = "sv-conclusion-changed";

const STATE_WORD: Record<string, string> = {
  not_proposed: "No conclusion recorded yet", proposed: "Proposed: waiting for the checker", approved: "Approved by the checker", returned: "Returned by the checker",
};

export function MmsgPanel({ validationId, text, onChanged }: { validationId: string; text?: string; onChanged?: () => void }) {
  const [version, setVersion] = React.useState(0);
  const load = useLoad(() => monitor.conclusion(validationId), `mmsg-${validationId}-${version}`);
  const [choice, setChoice] = React.useState<ConclusionId | "">("");
  const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  if (load.error) return <p className="text-sm text-negative" role="alert">{load.error}</p>;
  if (!load.data) return <Skeleton className="h-32 w-full" />;
  const c: ConclusionView = load.data;
  const rec = c.record;
  const picked = (choice || rec.conclusion || c.proposed.conclusion) as ConclusionId;
  const act = async (fn: () => Promise<ConclusionView>) => {
    setBusy(true);
    setError("");
    try {
      await fn(); setVersion((n) => n + 1); setNote(""); onChanged?.();
      // The thread's earlier single-step review follows an approved conclusion: tell it to reload.
      if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(CONCLUSION_EVENT, { detail: validationId }));
    }
    catch (e) { setError(friendlyMessage(e)); }
    finally { setBusy(false); }
  };
  return (
    <Card className="space-y-3 p-4" data-testid="sm-mmsg" data-state={rec.state}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">MMSG validation report · conclusion</p>
          <p className="text-[13px] text-text-secondary">{text ?? "The MMSG validation report for this validation, with the conclusion and its maker-checker record."}</p>
        </div>
        <a href={mmsgHref(validationId)} data-testid="sm-mmsg-download"
           className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-contrast"><FileText size={13} /> MMSG report (Word)</a>
      </div>
      <div className="rounded-md border border-border bg-surface-sunken p-2.5 text-[12px]" data-testid="sm-mmsg-proposed">
        <p><span className="text-text-muted">The rules propose </span><span className="font-semibold text-text-primary">{c.proposed.label}</span>: {c.proposed.reasons.join("; ")}.</p>
      </div>
      <p className="text-[12px]" data-testid="sm-mmsg-state"><span className="font-semibold text-text-primary">{STATE_WORD[rec.state] ?? rec.state}</span>
        {rec.conclusion ? <> · {c.conclusions[rec.conclusion]}</> : null}
        {rec.maker ? <span className="text-text-muted"> · maker {rec.maker}{rec.maker_at ? ` (${day(rec.maker_at)})` : ""}</span> : null}
        {rec.checker ? <span className="text-text-muted"> · checker {rec.checker}{rec.checker_at ? ` (${day(rec.checker_at)})` : ""}</span> : null}</p>
      {rec.note ? <p className="text-[12px] text-text-secondary">Maker&apos;s note: {rec.note}</p> : null}
      {rec.checker_note ? <p className="text-[12px] text-text-secondary">Checker&apos;s note: {rec.checker_note}</p> : null}
      {rec.state !== "approved" ? (
        <div className="space-y-2" data-testid="sm-mmsg-form">
          {rec.state !== "proposed" ? (
            <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Conclusion">
              {(Object.keys(c.conclusions) as ConclusionId[]).map((k) => (
                <button key={k} type="button" role="radio" aria-checked={picked === k} onClick={() => setChoice(k)} data-testid={`sm-mmsg-choose-${k}`}
                        className={cn("rounded-full border px-3 py-1 text-[12px]", picked === k ? "border-accent bg-accent/10 font-semibold text-text-primary" : "border-border text-text-secondary")}>
                  {c.conclusions[k]}</button>))}
            </div>) : null}
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} data-testid="sm-mmsg-note"
                    placeholder={rec.state === "proposed" ? "Checker's note" : "Maker's note: conditions, overlay, dates"}
                    className="w-full resize-none rounded-md border border-border bg-surface px-2.5 py-1.5 text-[12px] focus:border-accent focus:outline-none" />
          <div className="flex flex-wrap items-center gap-2">
            {rec.state !== "proposed" ? (
              <button type="button" disabled={busy} data-testid="sm-mmsg-propose" onClick={() => void act(() => monitor.propose(validationId, { conclusion: picked, note }))}
                      className="rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-contrast disabled:opacity-40">Propose as maker</button>) : (
              <>
                <button type="button" disabled={busy} data-testid="sm-mmsg-approve" onClick={() => void act(() => monitor.decide(validationId, { approve: true, note }))}
                        className="rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-contrast disabled:opacity-40">Approve as checker</button>
                <button type="button" disabled={busy} data-testid="sm-mmsg-return" onClick={() => void act(() => monitor.decide(validationId, { approve: false, note }))}
                        className="rounded-md border border-border px-3 py-1.5 text-[12px] disabled:opacity-40">Return to the maker</button>
              </>)}
            <span className="text-[11px] text-text-muted">Four eyes: the checker must be someone other than the maker, from Risk, Model Validation or the Administrator.</span>
          </div>
          {error ? <p className="text-[12px] text-negative" role="alert" data-testid="sm-mmsg-error">{error}</p> : null}
        </div>) : null}
    </Card>
  );
}
