"use client";

/**
 * R15 b (L11): on the Proposal check step,
 *
 *   <RmBrief res={result} sendBackUrl={…} />        "Brief for the RM": one page, numbered queries grouped by severity (critical
 *                                                   first) then section, each with the bank's evidence and the due date; edited
 *                                                   before sending; Send to RM (Mail), Copy, Word
 *   <ProposalDocButton res={result} />              "View the proposal": the RM's document itself (the uploaded Word or the
 *                                                   submission record), section by section on the left, the check's comments
 *                                                   anchored to each section on the right
 *
 * The brief text is written by the backend's deterministic writer (proposal_check/section_detail.rm_brief).
 */

import * as React from "react";
import { CheckCircle2, ClipboardCopy, Download, FileText, Loader2, Mail, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { core } from "@/lib/v5/core";

import { Chip, PrimaryButton, SecondaryButton } from "../kit";
import { fileHref, getJson } from "../papers/paper-view";
import { type CheckResult, type DocSection, briefHtml, checkUrls, matchUser, SEVERITY_TONE } from "./model";

export function RmBrief({ res, sendBackUrl }: { res: CheckResult; sendBackUrl: string }) {
  const b = res.brief;
  const [open, setOpen] = React.useState(false);
  const [text, setText] = React.useState(b?.text ?? "");
  const [msg, setMsg] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { setText(b?.text ?? ""); setMsg(""); }, [b?.text]);
  if (!b || !b.count) return null;

  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setMsg("Brief copied."); } catch { setMsg("Copy is not allowed in this browser: select the text and copy it."); }
  };
  const send = async () => {
    setBusy(true);
    setMsg("");
    try {
      // the send-back record (dd_proposal_quality rows marked sent_to_rm) is written first, then the Mail message
      await getJson<{ message: string }>(sendBackUrl, { method: "POST", body: JSON.stringify({ to: b.to }) });
      let mailed = "";
      try {
        const users = (await core.users()).users;
        const u = matchUser(b.to, users);
        if (u) {
          const subject = (text.split("\n").find((l) => l.startsWith("Subject: ")) ?? `Subject: ${b.subject}`).slice("Subject: ".length);
          const body = text.split("\n").filter((l) => !l.startsWith("To: ") && !l.startsWith("Subject: ")).join("\n").trim();
          await core.send({ to: [u.username], cc: [], subject, body_html: briefHtml(body), attachments: [], mode: "new" });
          mailed = ` and mailed to ${u.name} (Mail → Sent)`;
        } else {
          mailed = `; ${b.to} has no Mail account here, so copy the brief into your own mail`;
        }
      } catch {
        mailed = "; Mail is not reachable right now, so copy the brief into your own mail";
      }
      setMsg(`${b.count} queries recorded as sent back to ${b.to}${mailed}.`);
    } catch {
      setMsg("The brief could not be sent just now. Please try again in a moment.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="rounded-md border border-accent/30 bg-accent-muted/40 px-3 py-2" data-testid="dealdesk-rm-brief">
      <div className="flex flex-wrap items-center gap-2">
        <FileText size={14} className="text-accent" aria-hidden />
        <p className="text-[13px] font-semibold text-text-primary">Brief for the RM</p>
        <span className="text-[12px] text-text-secondary" data-testid="dealdesk-rm-brief-line">
          {b.count} queries{b.critical ? `, ${b.critical} critical first` : ""} · to {b.to} · reply by {b.due}</span>
        <div className="ml-auto flex flex-wrap gap-2">
          <SecondaryButton onClick={() => setOpen((x) => !x)} data-testid="dealdesk-rm-brief-toggle">{open ? "Hide the brief" : "Open the brief"}</SecondaryButton>
        </div>
      </div>
      {open ? (
        <div className="mt-2 space-y-2">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={Math.min(24, Math.max(10, text.split("\n").length + 1))}
                    aria-label="Brief for the RM (editable)" data-testid="dealdesk-rm-brief-text"
                    className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[12px] leading-5 text-text-primary" />
          <div className="flex flex-wrap items-center gap-2">
            <PrimaryButton onClick={send} disabled={busy || !text.trim()} data-testid="dealdesk-rm-brief-send">
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Mail size={14} />} Send to RM (Mail)</PrimaryButton>
            <SecondaryButton onClick={copy} data-testid="dealdesk-rm-brief-copy"><ClipboardCopy size={13} /> Copy</SecondaryButton>
            <a href={fileHref(res.links.queries)} data-testid="dealdesk-rm-brief-word"><SecondaryButton><Download size={13} /> Word</SecondaryButton></a>
            {text !== b.text ? <SecondaryButton onClick={() => setText(b.text)} data-testid="dealdesk-rm-brief-reset">Undo my edits</SecondaryButton> : null}
          </div>
          {msg ? <p className="text-[12px] text-text-secondary" data-testid="dealdesk-rm-brief-msg"><CheckCircle2 size={13} className="mr-1 inline text-positive" />{msg}</p> : null}
        </div>) : null}
    </div>
  );
}

export function ProposalDocButton({ res, label = "View the proposal", testId = "dealdesk-view-proposal", autoOpen = false }: { res: CheckResult; label?: string; testId?: string; autoOpen?: boolean }) {
  const [open, setOpen] = React.useState(autoOpen);
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  if (!res.document_view?.length) return null;
  return (
    <>
      <SecondaryButton onClick={() => setOpen(true)} data-testid={testId}><FileText size={13} /> {label}</SecondaryButton>
      {open ? (
        <div role="dialog" aria-modal="true" aria-label="The RM's proposal" data-testid="dealdesk-proposal-doc-dialog"
             className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-3" onClick={() => setOpen(false)}>
          <div className="relative flex h-[calc(100vh-1.5rem)] w-full max-w-[1320px] flex-col overflow-hidden rounded-xl bg-surface-sunken shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 border-b border-border bg-surface px-5 py-3 pr-12">
              <FileText size={16} className="text-accent" aria-hidden />
              <h2 className="text-[15px] font-semibold text-text-primary">The RM&apos;s proposal</h2>
              <span className="text-[12px] text-text-muted">{res.customer} · {res.document}{res.document_kind === "record" ? " (no Word on file: the submission record)" : ""} · {res.rm}</span>
              <button type="button" onClick={() => setOpen(false)} aria-label="Close" data-testid="dealdesk-proposal-doc-close"
                      className="absolute right-3 top-3 inline-flex size-7 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover"><X size={15} /></button>
            </div>
            <ProposalDocView sections={res.document_view} />
          </div>
        </div>) : null}
    </>
  );
}

export function ProposalDocView({ sections }: { sections: DocSection[] }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4" data-testid="dealdesk-proposal-doc">
      <div className="mx-auto grid max-w-[1240px] grid-cols-[minmax(0,1fr)_340px] gap-x-4">
        <p className="pb-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted">The document</p>
        <p className="pb-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted">The check&apos;s comments</p>
        {sections.map((s, i) => (
          <React.Fragment key={`${s.key}-${i}`}>
            <section className="border-t border-border bg-surface px-4 py-3" data-section={s.key}>
              <h4 className="text-[13px] font-semibold text-accent">{s.heading}</h4>
              {s.paras.map((p, j) => <p key={j} className="mt-1 text-[12.5px] leading-5 text-text-primary">{p}</p>)}
              {s.tables.map((t, j) => (
                <table key={`t${j}`} className="mt-2 w-full border-collapse text-[11.5px]">
                  <tbody>{t.map((row, r) => <tr key={r} className={r === 0 ? "font-semibold" : undefined}>{row.map((c, k) => <td key={k} className="border border-border px-1.5 py-0.5">{c}</td>)}</tr>)}</tbody>
                </table>))}
              {!s.paras.length && !s.tables.length ? <p className="mt-1 text-[12px] italic text-text-muted">(heading only, no text)</p> : null}
            </section>
            <aside className="space-y-1.5 border-t border-border px-1 py-3" data-testid="dealdesk-proposal-doc-comments" data-section={s.key}>
              {s.comments.length ? s.comments.map((c, j) => (
                <div key={j} className={cn("rounded-md border bg-surface px-2 py-1.5 text-[11.5px]", c.severity === "critical" ? "border-negative/50" : "border-border")}>
                  <Chip tone={SEVERITY_TONE[c.severity] ?? "neutral"}>{c.result === "observation" ? "note" : c.severity}</Chip>
                  <p className="mt-1 text-text-primary">{c.title}</p>
                  {c.claim ? <p className="text-text-muted">The paper says: &ldquo;{c.claim}&rdquo;</p> : null}
                  {c.evidence ? <p className="text-text-muted">Bank&apos;s evidence: {c.evidence}</p> : null}
                  {c.query ? <p className="text-text-secondary">Query: {c.query}</p> : null}
                </div>)) : <p className="text-[11.5px] text-text-muted">No comment on this section.</p>}
            </aside>
          </React.Fragment>))}
      </div>
    </div>
  );
}

/** The same view from Review → The memo and More → Documents: loads the proposal check on the first click. */
export function ProposalDocFromCheck({ proposalId, label = "View the RM's proposal", testId = "dealdesk-view-rm-proposal" }: { proposalId: string; label?: string; testId?: string }) {
  const [res, setRes] = React.useState<CheckResult | null>(null);
  const [state, setState] = React.useState<"" | "busy" | "none">("");
  const load = () => {
    setState("busy");
    getJson<CheckResult>(checkUrls(proposalId).run).then((r) => { setRes(r); setState(""); }, () => setState("none"));
  };
  if (res) return <ProposalDocButton res={res} label={label} testId={testId} autoOpen />;
  return (
    <span className="inline-flex items-center gap-2">
      <SecondaryButton onClick={load} disabled={state === "busy"} data-testid={testId}>
        {state === "busy" ? <Loader2 size={13} className="animate-spin" /> : <FileText size={13} />} {label}</SecondaryButton>
      {state === "none" ? <span className="text-[11.5px] text-text-muted" data-testid={`${testId}-none`}>No RM proposal on file for this deal yet.</span> : null}
    </span>);
}
