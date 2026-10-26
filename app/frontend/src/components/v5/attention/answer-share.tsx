"use client";

import { ShareButton } from "@/components/v5/mail/share";
import { CockpitAnswerActions } from "@/components/v5/thread/cockpit-actions";

/**
 * "Share in Mail" on a Cockpit answer (FX-5): sends the conversation to colleagues through CreditProbe Mail.
 * R16 t (M7): followed by the shared thread actions (Trace, Word, Add to report; Share where this button is absent,
 * i.e. on past answers, which the frozen thread draws without a thread id).
 */
export function AnswerMailShare({ question, threadId, runId }: { question: string; threadId?: string; runId: string }) {
  return (
    <>
      {threadId ? (
        <ShareButton testId="v4-action-share-mail" label="Share in Mail" size="sm" variant="outline"
                     object={{ type: "cockpit-thread", id: threadId, label: `Cockpit: ${question.slice(0, 150)}`,
                               href: `/cockpit/thread/${encodeURIComponent(threadId)}`,
                               summary: question.slice(0, 300), meta: { run_id: runId } }} />) : null}
      <CockpitAnswerActions question={question} threadId={threadId} runId={runId} hasMailShare={Boolean(threadId)} />
    </>
  );
}
