"use client";

/**
 * PLAN_R11 P6 (Session O): Deal Desk Parameters → Learn from documents.
 *
 * Upload the bank's credit policy, its memos and optionally the DoA matrix and the risk appetite statement. The answer
 * first (what was learned, what conflicts with the CBUAE CRM Standards, what a person must check), then the conflicts
 * and gaps, the maker-checker list, the accepted versions and a timed draft-and-review with the accepted version.
 */

import * as React from "react";

import { InfoPopover } from "./explain"; // R12 G (I6): the bounded Deal Desk (i)
import { Skeleton } from "@/components/ui/skeleton";
import { BackButton } from "@/components/v5/core/back-button";
import { KpiRow } from "@/components/v5/core/kpi-row";
import { cn } from "@/lib/utils";
import {
  type DraftReview, type Item, type Overview, type Session, answerLine, headlineText, onboard, secs,
} from "@/lib/v5/dealdesk-onboard";

import { Chip, PrimaryButton, Section, SecondaryButton, tableCls, tdCls, thCls } from "./kit";
import { OnboardItems } from "./onboard-items";

const TRY = [
  { id: "PRP-A-GMC", label: "Case A: Gulf Meridian Contracting" }, { id: "PRP-B-ASB", label: "Case B: Al Sahel Building Materials" },
  { id: "DD-01", label: "DD-01" }, { id: "DD-02", label: "DD-02" }, { id: "DD-06", label: "DD-06" },
];

function FileField({ label, multiple, onFiles, testId, info }: { label: string; multiple?: boolean; onFiles: (f: File[]) => void; testId: string; info: string }) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-[12px] text-text-secondary">
      <span className="inline-flex items-center gap-1 font-medium text-text-primary">{label}<InfoPopover title={label}>{info}</InfoPopover></span>
      <input type="file" multiple={multiple} accept=".docx,.pdf,.md,.txt" data-testid={testId}
             onChange={(e) => onFiles(Array.from(e.target.files ?? []))}
             className="min-w-0 text-[12px] file:mr-2 file:h-7 file:rounded-md file:border file:border-border file:bg-surface file:px-2 file:text-[12px]" />
    </label>
  );
}

export function OnboardPage() {
  const [ov, setOv] = React.useState<Overview | null>(null);
  const [s, setS] = React.useState<Session | null>(null);
  const [err, setErr] = React.useState("");
  const [msg, setMsg] = React.useState("");
  const [busy, setBusy] = React.useState("");
  const [files, setFiles] = React.useState<{ policy: File[]; memos: File[]; doa: File[]; appetite: File[] }>({ policy: [], memos: [], doa: [], appetite: [] });
  const [tryId, setTryId] = React.useState(TRY[0].id);
  const [dr, setDr] = React.useState<DraftReview | null>(null);

  const load = React.useCallback(() => {
    onboard.overview().then((o) => { setOv(o); setS(o.session); }, (e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);
  React.useEffect(() => { load(); }, [load]);

  const run = (what: string, p: Promise<Session>) => {
    setBusy(what); setErr(""); setMsg(""); setDr(null);
    const t0 = performance.now();
    p.then((x) => { setS(x); setMsg(`Read ${x.documents.length} documents in ${secs((performance.now() - t0) / 1000)}. Everything below is proposed.`); onboard.overview().then(setOv, () => {}); },
      (e: unknown) => setErr(e instanceof Error ? e.message : String(e))).finally(() => setBusy(""));
  };
  const learn = () => {
    if (!files.policy[0]) { setErr("Choose the bank's credit policy first."); return; }
    run("learn", onboard.learn({ policy: files.policy[0], memos: files.memos, doa: files.doa[0] ?? null, appetite: files.appetite[0] ?? null }));
  };
  const decide = (it: Item, action: "accept" | "edit" | "reject", value?: unknown) => {
    if (!s) return;
    setBusy(it.id); setErr("");
    onboard.decide(s.session_id, it.id, action, value).then((r) => {
      setMsg(r.version ? `${it.label}: accepted into version ${r.version.version}.` : `${it.label}: rejected.`);
      return onboard.session(s.session_id).then(setS).then(() => onboard.overview().then(setOv));
    }, (e: unknown) => setErr(e instanceof Error ? e.message : String(e))).finally(() => setBusy(""));
  };
  const tryIt = () => {
    setBusy("try"); setErr(""); setDr(null);
    onboard.draftReview(tryId).then(setDr, (e: unknown) => setErr(e instanceof Error ? e.message : String(e))).finally(() => setBusy(""));
  };

  const sm = s?.summary;
  const versions = ov?.versions ?? [];
  return (
    <div className="space-y-4" data-testid="onboard-page">
      <BackButton fallback={{ href: "/deal-desk/parameters", label: "Deal Desk Parameters" }} testId="onboard-back" />
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Deal Desk Parameters</p>
          <div className="flex items-center gap-2"><h1 className="text-2xl font-semibold text-text-primary">Learn from documents</h1>
            <InfoPopover title="Learn from documents">Upload the bank&apos;s credit policy and its memos. CreditProbe reads every clause with a threshold or a
              condition and proposes it as a review rule or a Deal Desk parameter, with the clause it came from; compares the policy with the CBUAE
              Credit Risk Management Standards; learns the memo structure, the house language and the questions committees ask. Nothing applies
              until a checker accepts it.</InfoPopover></div>
        </div>
      </div>

      <Section title="Documents" testId="onboard-upload"
               info="A .docx, .pdf (with a text layer), .md or .txt. The policy is required; memos teach the structure, the house language and the committee questions.">
        <div className="grid gap-3 md:grid-cols-4">
          <FileField label="Credit policy" testId="onboard-file-policy" onFiles={(f) => setFiles({ ...files, policy: f })} info="The bank's credit policy: numbered clauses and tables." />
          <FileField label="Memos" multiple testId="onboard-file-memos" onFiles={(f) => setFiles({ ...files, memos: f })} info="Past credit memos, approved and declined, with the committee's decision, conditions and comments." />
          <FileField label="DoA matrix (optional)" testId="onboard-file-doa" onFiles={(f) => setFiles({ ...files, doa: f })} info="The Delegation of Authority matrix, if it is not an appendix of the policy." />
          <FileField label="Risk appetite statement (optional)" testId="onboard-file-appetite" onFiles={(f) => setFiles({ ...files, appetite: f })} info="Limits stated in the risk appetite statement." />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <PrimaryButton onClick={learn} disabled={!!busy} data-testid="onboard-learn">{busy === "learn" ? "Reading…" : "Learn"}</PrimaryButton>
          <SecondaryButton onClick={() => run("demo", onboard.demo())} disabled={!!busy} data-testid="onboard-demo">{busy === "demo" ? "Reading…" : "Use sample documents"}</SecondaryButton>
          <InfoPopover title="Sample documents">A fictional bank&apos;s credit policy, four of its committee memos and the house&apos;s memos.</InfoPopover>
        </div>
      </Section>

      {msg ? <p className="text-[12px] text-positive" data-testid="onboard-msg">{msg}</p> : null}
      {err ? <p role="alert" className="text-[12px] text-negative">{err}</p> : null}
      {!ov && !err ? <Skeleton className="h-40 w-full" /> : null}

      {s && sm ? (
        <>
          <p className="text-[14px] font-medium text-text-primary" data-testid="onboard-answer">{answerLine(s)}</p>
          <KpiRow testId="onboard-tiles" tiles={[
            { label: "Learned", value: `${sm.rules} rules · ${sm.params} parameters`, sub: `${sm.thresholds} thresholds, ${sm.conditions} conditions`,
              info: "Clauses with a threshold or a condition, as rules in the review rule book's schema and as Deal Desk parameters (risk appetite, DoA, market bounds, desk)." },
            { label: "Weaker than CBUAE CRM", value: String(sm.conflicts), tone: sm.conflicts ? "negative" : "positive", sub: "clauses to amend",
              info: "Policy numbers less strict than the CBUAE Credit Risk Management Standards. The stricter applies; each is quoted against its article." },
            { label: "Checked by a person", value: `${sm.manual} of ${sm.manual + sm.auto}`, tone: sm.manual ? "warning" : "positive", sub: `${sm.section_gaps} required sections skipped`,
              info: "Rules the bank's data cannot check (no field holds the input), and sections the policy requires that the memos skip." },
            { label: "Accepted", value: `${sm.accepted} of ${sm.items}`, sub: `${sm.rejected} rejected · ${sm.pending} pending`, tone: sm.accepted ? "positive" : "neutral",
              info: "Items a checker accepted. Each accept writes the next version; nothing applies until accepted." },
          ]} />

          <Section title="Conflicts and gaps" testId="onboard-conflicts"
                   info="Clauses weaker than the CBUAE CRM Standards (quoted from the Standards in Policy Docs), sections the policy requires that the memos skip, and rules no data can check.">
            <table className={tableCls}>
              <thead><tr>{["Clause", "Finding", "Policy", "Regulation"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
              <tbody>
                {s.conflicts.map((c) => (
                  <tr key={c.id} data-testid="onboard-conflict">
                    <td className={cn(tdCls, "font-medium")}>{c.clause}</td>
                    <td className={cn(tdCls, "max-w-[420px] whitespace-normal")}><Chip tone="negative">Weaker than regulation</Chip> <span className="ml-1">{c.label}</span>
                      <InfoPopover title={c.regulation}><p className="italic">Policy: “{c.quote}”</p><p className="mt-2 italic">{c.regulation}: “{c.regulation_quote}”</p></InfoPopover></td>
                    <td className={tdCls}>{c.policy_value} {c.unit}</td>
                    <td className={tdCls}><a className="underline-offset-2 hover:underline" href={c.href}>{c.regulation}</a>: {c.regulation_value} {c.unit}</td>
                  </tr>))}
                {s.gaps.sections.map((g) => (
                  <tr key={g.id} data-testid="onboard-gap-section">
                    <td className={cn(tdCls, "font-medium")}>{g.clause}</td>
                    <td className={cn(tdCls, "max-w-[420px] whitespace-normal")}><Chip tone="warning">Section skipped</Chip> <span className="ml-1">{g.section}</span></td>
                    <td className={tdCls}>required</td><td className={tdCls}>{g.missing} of {g.of} memos without it</td>
                  </tr>))}
                {s.gaps.data.map((g) => (
                  <tr key={g.id} data-testid="onboard-gap-data">
                    <td className={cn(tdCls, "font-medium")}>{g.clause}</td>
                    <td className={cn(tdCls, "max-w-[420px] whitespace-normal")}><Chip tone="neutral">No data</Chip> <span className="ml-1">{g.message}</span></td>
                    <td className={tdCls} colSpan={2}>checked by a person</td>
                  </tr>))}
              </tbody>
            </table>
          </Section>

          <OnboardItems session={s} busy={busy} onDecide={decide} />

          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Accepted versions" testId="onboard-versions"
                     info="Each accept writes the whole rule book and the changed parameter tables as the next version, every changed row with where it was learned from and who accepted it. The live tables change only when their owners promote a version.">
              {!versions.length ? <p className="text-[12px] text-text-muted">No version yet: nothing has been accepted.</p> : (
                <div className="max-h-[260px] overflow-auto"><table className={tableCls}>
                  <thead><tr>{["Version", "Items", "Rules added", "Tables", "By"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
                  <tbody>{[...versions].reverse().slice(0, 30).map((v) => (
                    <tr key={v.version} data-testid="onboard-version"><td className={cn(tdCls, "font-medium")}>{v.version}</td><td className={tdCls}>{v.accepted_items.length}</td>
                      <td className={tdCls}>{v.rules_added}</td><td className={tdCls}>{v.params_changed.join(", ") || "none"}</td><td className={tdCls}>{v.by}</td></tr>))}</tbody>
                </table></div>)}
            </Section>

            <Section title="Draft and review with the accepted version" testId="onboard-try"
                     info="Drafts the proposal in the house style with the accepted committee questions answered where the data allows, then reviews it: the proposal review, the accepted policy rules and the questions the draft leaves open. Timed.">
              <div className="flex flex-wrap items-center gap-2">
                <select value={tryId} onChange={(e) => setTryId(e.target.value)} aria-label="Proposal" data-testid="onboard-try-select"
                        className="h-8 rounded-md border border-border bg-surface px-2 text-[12px]">
                  {TRY.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select>
                <PrimaryButton onClick={tryIt} disabled={!!busy || !versions.length} data-testid="onboard-try-run">{busy === "try" ? "Drafting…" : "Draft and review"}</PrimaryButton>
              </div>
              {dr ? (
                <div className="mt-3 space-y-2 text-[12px]" data-testid="onboard-try-result">
                  <p className="font-medium text-text-primary">{headlineText(dr.review.headline) || "Reviewed"}; {dr.review.policy_findings} policy finding{dr.review.policy_findings === 1 ? "" : "s"};{" "}
                    {dr.review.open_questions.length} committee question{dr.review.open_questions.length === 1 ? "" : "s"} left open.</p>
                  <p className="text-text-secondary">Drafted in {secs(dr.timings.draft_s)} (style score {dr.style_score ?? "n/a"}), reviewed in {secs(dr.timings.draft_to_review_s)} with {dr.version}.</p>
                  <ul className="space-y-1">{dr.committee_answers.map((a) => (
                    <li key={a.id} className="flex gap-2"><Chip tone={a.status === "answered" ? "positive" : "warning"}>{a.status === "answered" ? "Answered" : "Open"}</Chip>
                      <span>{a.question}{a.where ? <span className="text-text-muted"> · {a.where}</span> : null}</span></li>))}</ul>
                </div>) : null}
            </Section>
          </div>
        </>
      ) : ov && !busy ? <p className="text-[12px] text-text-muted" data-testid="onboard-empty">No documents read yet.</p> : null}
    </div>
  );
}
