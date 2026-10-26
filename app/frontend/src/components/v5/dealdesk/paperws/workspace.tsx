"use client";

/**
 * Rounds W and T: the proposal workspace. The document on the left (the bank-form section/blocks model, as the Word prints it),
 * the conversation with Noor on the right, wired to this document. Every instruction edits ONE section in place and the change
 * is marked (before / after, Accept / Undo); every change is a version (v1, v2… who, when, instruction); Word and PDF at any
 * time (with the provenance annex); "Mark final" sets the committee copy. Click a point to see its evidence; "Provenance" shows
 * the whole paper's (Round T). A number goes to the structure step, never into the text (backend/dealdesk/paperws).
 *
 *   <ProposalWorkspace wsId="PW-…" onInstructionApplied={(section, instruction) => …} />   // the page /deal-desk/paper/[paperId]
 *
 * Round K mounts "Save this as a rule?" through ./hooks (registerAfterInstruction / registerInstructionApplied).
 */

import { useRouter } from "next/navigation";
import * as React from "react";
import { ArrowLeft, ArrowUp, Check, Download, FileText, History, ListTree, Loader2, RotateCcw, Stamp, X } from "lucide-react";

import { MicButton } from "@/components/noor/mic-button";
import { openPanel, useNoor } from "@/components/noor/noor-store";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";

import { Chip, PrimaryButton, SecondaryButton } from "../kit";
import { errorText, fileHref, getJson } from "../papers/paper-view";
import { BlockView, Rich } from "../proposal/blocks";
import type { Block } from "../proposal/model";
import { type AfterInstructionProps, type AppliedSection, afterInstructionComponent, emitInstructionApplied, registerAfterInstruction } from "./hooks";
import {
  type Evidence, EVIDENCE_LABEL, type Provenance, type PvPoint, type PwPending, type PwSection, type PwState, type PwTurn,
  busyLine, evidenceText, lineDiff, ordered, pendingBySection, pointIndex, pwUrls, sectionNo, suggestions, versionLine,
} from "./model";
import { ProvenanceView } from "./provenance-view";
import { AfterInstructionRulePrompt } from "@/components/v5/rules/save-rule-prompt";

// Round K × W: "Save this as a rule for your future documents?" under every instruction Noor applies.
registerAfterInstruction(AfterInstructionRulePrompt);

const BOXED = new Set(["action", "recommendation"]);
const KIND_TONE: Record<Evidence["kind"], "accent" | "neutral" | "positive" | "warning" | "negative"> = {
  document: "accent", data: "neutral", engine: "positive", rule: "warning", analyst: "warning", rm: "accent",
};

export function ProposalWorkspace({ wsId, initialView = "document", initialFocus, onInstructionApplied }: {
  wsId: string; initialView?: "document" | "provenance";
  /** Point Noor at this section on open (e.g. "Draft this section from data"). */
  initialFocus?: string;
  /** Called after every instruction that changed the document (Round K's "Save this as a rule?"). */
  onInstructionApplied?: (section: AppliedSection, instruction: string) => void;
}) {
  const router = useRouter();
  const [st, setSt] = React.useState<PwState | null>(null);
  const [error, setError] = React.useState("");
  const [view, setView] = React.useState<"document" | "provenance">(initialView);
  const [viewVersion, setViewVersion] = React.useState<number | null>(null);
  const [old, setOld] = React.useState<PwState | null>(null);
  const [showVersions, setShowVersions] = React.useState(false);
  const [focus, setFocus] = React.useState<string | null>(initialFocus ?? null);
  const [busy, setBusy] = React.useState("");
  const [pv, setPv] = React.useState<Provenance | null>(null);
  const [pvFor, setPvFor] = React.useState("");
  const [openPoint, setOpenPoint] = React.useState<string | null>(null);
  const [applied, setApplied] = React.useState<{ turnId: string; props: Omit<AfterInstructionProps, "onDone"> } | null>(null);
  const docRef = React.useRef<HTMLDivElement>(null);
  const scrollToRef = React.useRef<(key: string) => void>(() => undefined);

  // Noor's side panel and this conversation are the same Noor: the workspace's own panel replaces it while open.
  React.useEffect(() => { openPanel(false); }, []);
  React.useEffect(() => {
    let live = true;
    getJson<PwState>(pwUrls.one(wsId)).then((s) => { if (live) setSt(s); }, (e: unknown) => { if (live) setError(errorText(e)); });
    return () => { live = false; };
  }, [wsId]);
  React.useEffect(() => {
    if (viewVersion == null) { setOld(null); return; }
    let live = true;
    getJson<PwState>(pwUrls.one(wsId, viewVersion)).then((s) => { if (live) setOld(s); }, (e: unknown) => { if (live) setError(errorText(e)); });
    return () => { live = false; };
  }, [wsId, viewVersion]);

  const landed = React.useRef(false);
  React.useEffect(() => {  // land on the section asked for once the document is drawn
    if (!st || landed.current || !initialFocus) return;
    landed.current = true;
    window.setTimeout(() => scrollToRef.current(initialFocus), 80);
  }, [st, initialFocus]);
  const shown = old ?? st;
  const versionKey = `${wsId}|${shown?.version.n ?? 0}`;
  const needPv = view === "provenance" || openPoint !== null;
  React.useEffect(() => {
    if (!needPv || !shown || pvFor === versionKey) return;
    let live = true;
    getJson<Provenance>(pwUrls.provenance(wsId, shown.version.n)).then((p) => { if (live) { setPv(p); setPvFor(versionKey); } }, () => undefined);
    return () => { live = false; };
  }, [needPv, shown, versionKey, pvFor, wsId]);

  const scrollTo = React.useCallback((key: string) => {
    const el = docRef.current?.querySelector(`[data-section="${key}"]`);
    if (el && "scrollIntoView" in el) (el as HTMLElement).scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);
  scrollToRef.current = scrollTo;

  const send = async (text: string) => {
    if (!st || !text.trim() || busy) return;
    setBusy(busyLine(text, st.workspace.kind));
    setViewVersion(null);
    try {
      const next = await getJson<PwState>(pwUrls.instruct(wsId), { method: "POST", body: JSON.stringify({ text, focus }) });
      setSt(next);
      const last = next.last;
      if (last && (last.kind === "edit" || last.kind === "structure") && last.version) {
        const key = last.section ?? "";
        const s = next.paper.sections.find((x) => x.key === key);
        const section = { key, heading: s?.heading ?? key };
        const ctx = { wsId, kind: next.workspace.kind, proposalId: next.workspace.proposal_id, version: last.version, structure: last.kind === "structure" };
        emitInstructionApplied(section, text, ctx);
        onInstructionApplied?.(section, text);
        const turn = [...next.turns].reverse().find((t) => t.role === "noor");
        if (turn) setApplied({ turnId: turn.turn_id, props: { section, instruction: text, wsId, kind: ctx.kind, proposalId: ctx.proposalId, version: last.version } });
        if (key) window.setTimeout(() => scrollTo(key), 60);
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  };

  const act = async (url: string, body?: unknown) => {
    if (busy) return;
    setBusy("Saving…");
    try {
      setSt(await getJson<PwState>(url, { method: "POST", body: JSON.stringify(body ?? {}) }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  };

  if (error && !st) {
    return <p role="alert" className="p-6 text-[13px] text-negative" data-testid="pw-error">The workspace could not be opened: {error}</p>;
  }
  if (!st || !shown) {
    return (
      <div className="flex h-[60vh] items-center justify-center gap-2 text-[13px] text-text-muted" data-testid="pw-loading">
        <Loader2 className="animate-spin" size={16} /> Opening the document…</div>);
  }
  const w = st.workspace;
  const p = shown.paper;
  const marks = old ? new Map() : pendingBySection(st.pending);
  const focusSec = p.sections.find((s) => s.key === focus) ?? null;
  const vq = viewVersion ?? undefined;

  return (
    <div className="flex h-[calc(100vh-5.5rem)] min-h-[560px] flex-col overflow-hidden rounded-xl border border-border bg-surface-sunken" data-testid="pw-workspace" data-ws={w.ws_id}>
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-4 py-2.5">
        <button type="button" onClick={() => (w.proposal_id && w.kind === "proposal" ? router.push(`/deal-desk/${encodeURIComponent(w.proposal_id)}`) : router.back())}
                aria-label="Back" data-testid="pw-back" className="inline-flex size-7 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover"><ArrowLeft size={15} /></button>
        <FileText size={16} className="text-accent" aria-hidden />
        <h1 className="text-[15px] font-semibold text-text-primary" data-testid="pw-title">{w.title}</h1>
        <span className="text-[12px] text-text-muted">{w.proposal_id}{p.as_of_label ? ` · as at ${p.as_of_label}` : ""}</span>
        <Chip tone="accent" testId="pw-version-chip">v{shown.version.n}{viewVersion ? " (read-only)" : ""}</Chip>
        {w.final_version ? <Chip tone="positive" testId="pw-final-chip" title="The committee copy">Final: v{w.final_version}</Chip> : <Chip testId="pw-draft-chip">Working draft</Chip>}
        {st.pending.length ? <Chip tone="warning" testId="pw-pending-chip">{st.pending.length} change{st.pending.length === 1 ? "" : "s"} to review</Chip> : null}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-md border border-border p-0.5" role="tablist" aria-label="View">
            {(["document", "provenance"] as const).map((k) => (
              <button key={k} type="button" role="tab" aria-selected={view === k} onClick={() => setView(k)} data-testid={`pw-view-${k}`}
                      className={cn("h-7 rounded px-3 text-[12px]", view === k ? "bg-accent font-medium text-accent-contrast" : "text-text-secondary hover:bg-surface-hover")}>
                {k === "document" ? "Document" : <span className="inline-flex items-center gap-1"><ListTree size={12} /> Provenance</span>}</button>))}
          </div>
          <SecondaryButton onClick={() => setShowVersions((x) => !x)} aria-pressed={showVersions} data-testid="pw-versions-toggle">
            <History size={13} /> Versions ({st.versions.length})</SecondaryButton>
          <a href={fileHref(pwUrls.docx(wsId, vq))} data-testid="pw-docx"><PrimaryButton><Download size={14} /> Word</PrimaryButton></a>
          <a href={fileHref(pwUrls.pdf(wsId, vq))} data-testid="pw-pdf"><SecondaryButton className="h-9"><Download size={13} /> PDF</SecondaryButton></a>
          <SecondaryButton onClick={() => void act(pwUrls.final(wsId), { version: shown.version.n })} disabled={!!busy || w.final_version === shown.version.n}
                           data-testid="pw-mark-final" title="This version becomes the committee copy (Word and PDF)">
            <Stamp size={13} /> {w.final_version === shown.version.n ? "Final" : "Mark final"}</SecondaryButton>
        </div>
      </div>

      {showVersions ? (
        <VersionList st={st} viewing={viewVersion} onView={(n) => { setViewVersion(n === st.workspace.current_version ? null : n); setOpenPoint(null); }} />) : null}
      {viewVersion ? (
        <div className="flex items-center gap-2 border-b border-border bg-warning/10 px-4 py-1.5 text-[12px] text-text-secondary" data-testid="pw-old-banner">
          Viewing version {viewVersion}, read-only. Word and PDF download this version.
          <button type="button" className="ml-auto text-accent underline" onClick={() => setViewVersion(null)} data-testid="pw-old-back">Back to the current version</button>
        </div>) : null}

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div ref={docRef} className="min-h-0 overflow-y-auto px-4 py-4" data-testid="pw-doc">
          {view === "provenance"
            ? <ProvenanceView pv={pvFor === versionKey ? pv : null} onOpen={(k) => { setView("document"); window.setTimeout(() => scrollTo(k), 60); }} />
            : <Doc st={shown} marks={marks} focus={focus} onFocus={setFocus} openPoint={openPoint} onPoint={(id) => setOpenPoint((x) => (x === id ? null : id))}
                   pv={pvFor === versionKey ? pv : null} busy={!!busy} readOnly={!!viewVersion}
                   onAccept={(n) => void act(pwUrls.accept(wsId, n))} onUndo={(n) => void act(pwUrls.undo(wsId, n))} />}
        </div>
        <Conversation st={st} focus={focusSec} onClearFocus={() => setFocus(null)} busy={busy} onSend={send} error={error} onDismissError={() => setError("")}
                      applied={applied} onAppliedDone={() => setApplied(null)} onShow={(k) => { setView("document"); setViewVersion(null); window.setTimeout(() => scrollTo(k), 60); }} />
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ the document

function Doc({ st, marks, focus, onFocus, openPoint, onPoint, pv, busy, readOnly, onAccept, onUndo }: {
  st: PwState; marks: Map<string, { version: number; change: { before: Block[]; after: Block[]; heading: string }; pending: PwPending }>;
  focus: string | null; onFocus: (k: string) => void; openPoint: string | null; onPoint: (id: string) => void; pv: Provenance | null;
  busy: boolean; readOnly: boolean; onAccept: (n: number) => void; onUndo: (n: number) => void;
}) {
  const p = st.paper;
  const pts = React.useMemo(() => pointIndex(pv), [pv]);
  const title = p.doc_kind === "request" ? "BUSINESS REQUEST" : "CREDIT PROPOSAL (BANK FORM)";
  return (
    <article className="mx-auto max-w-[860px] rounded-sm border border-border bg-surface shadow-sm" data-testid="pw-paper">
      <header className="border-b border-border px-6 pb-2 pt-3">
        <p className="text-[9px] font-semibold tracking-[0.08em] text-text-muted"><span className="text-accent">CREDITPROBE</span> · {title} · INTERNAL</p>
        {p.header_line?.length ? (
          <div className="mt-1 grid grid-cols-2 border-l border-t border-border text-[9.5px] sm:grid-cols-4">
            {p.header_line.map(([k, v]) => (
              <div key={k} className="flex min-w-0 border-b border-r border-border">
                <span className="w-[62px] shrink-0 bg-surface-sunken px-1 py-0.5 font-semibold text-text-muted">{k}</span>
                <span className="truncate px-1 py-0.5 text-text-primary" title={v}>{v}</span></div>))}
          </div>) : null}
      </header>
      <div className="space-y-3 px-6 py-4">
        {ordered(p).map(({ part, section: s }) => {
          const mark = marks.get(s.key);
          return (
            <React.Fragment key={s.key}>
              {part ? <div className="rounded-sm bg-accent px-3 py-1.5 text-[11px] font-semibold text-accent-contrast" data-testid="pw-part">
                {part.title}<span className="ml-2 font-normal opacity-80">{part.subtitle}</span></div> : null}
              <section data-section={s.key} data-testid={`pw-section-${s.key}`} onClick={() => onFocus(s.key)}
                       className={cn("scroll-mt-4 space-y-1.5 rounded-sm px-2 py-1.5 -mx-2", focus === s.key ? "ring-2 ring-accent/60" : "hover:bg-surface-hover/40",
                         mark && "border-l-4 border-warning bg-warning/5")}>
                <div className="flex flex-wrap items-baseline gap-2">
                  <h4 className="text-[13px] font-semibold text-accent">{sectionNo(p.sections, s.key, p.doc_kind)} {s.heading}</h4>
                  {s.edited && !mark ? <span className="text-[10px] text-text-muted" title={s.edited_by?.instruction}>edited by instruction</span> : null}
                  {s.gaps?.length ? <span className="text-[10px] text-warning" title={s.gaps.join(", ")}>information not provided: {s.gaps.length}</span> : null}
                </div>
                {mark ? <ChangeMark mark={mark} busy={busy} readOnly={readOnly} onAccept={onAccept} onUndo={onUndo} /> : null}
                <div className={cn("space-y-1.5", BOXED.has(s.key) && "rounded-sm border-2 border-text-primary/70 p-3")}>
                  {s.blocks.map((b, i) => <PointBlock key={i} s={s} b={b} i={i} openPoint={openPoint} onPoint={onPoint} pts={pts} />)}
                </div>
              </section>
            </React.Fragment>);
        })}
      </div>
    </article>
  );
}

function ChangeMark({ mark, busy, readOnly, onAccept, onUndo }: {
  mark: { version: number; change: { before: Block[]; after: Block[]; heading: string }; pending: PwPending };
  busy: boolean; readOnly: boolean; onAccept: (n: number) => void; onUndo: (n: number) => void;
}) {
  const d = lineDiff(mark.change.before, mark.change.after);
  const [open, setOpen] = React.useState(true);
  return (
    <div className="space-y-1 rounded-md border border-warning/50 bg-surface p-2 text-[11px]" data-testid="pw-mark" data-version={mark.version} onClick={(e) => e.stopPropagation()}>
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="warning">v{mark.version} · {mark.pending.action === "structure" ? "structure step" : "edited"}</Chip>
        <span className="min-w-0 flex-1 truncate text-text-secondary" title={mark.pending.instruction}>“{mark.pending.instruction}” · {mark.pending.author}</span>
        <button type="button" className="text-accent underline" onClick={() => setOpen((x) => !x)} data-testid="pw-mark-toggle">{open ? "Hide before" : "Show before"}</button>
        {!readOnly ? <>
          <SecondaryButton className="h-7 px-2 text-[11.5px]" disabled={busy} onClick={() => onAccept(mark.version)} data-testid="pw-accept"><Check size={12} /> Accept</SecondaryButton>
          <SecondaryButton className="h-7 px-2 text-[11.5px]" disabled={busy} onClick={() => onUndo(mark.version)} data-testid="pw-undo"><RotateCcw size={12} /> Undo</SecondaryButton>
        </> : null}
      </div>
      {mark.pending.fields?.length ? (
        <p className="text-text-muted" data-testid="pw-mark-fields">{mark.pending.fields.map((f) => `${f.label}: ${String(f.from ?? "–")} → ${String(f.to ?? "–")}`).join(" · ")}</p>) : null}
      {open ? (
        <div className="grid gap-2 sm:grid-cols-2" data-testid="pw-mark-diff">
          <div><p className="font-semibold text-text-muted">Before</p>
            <ul className="space-y-0.5">{d.removed.length ? d.removed.map((x, i) => <li key={i} className="text-negative line-through decoration-negative/60" data-testid="pw-mark-removed"><Rich text={x} /></li>)
              : <li className="text-text-muted">nothing removed</li>}</ul></div>
          <div><p className="font-semibold text-text-muted">After</p>
            <ul className="space-y-0.5">{d.added.length ? d.added.map((x, i) => <li key={i} className="text-positive" data-testid="pw-mark-added"><Rich text={x} /></li>)
              : <li className="text-text-muted">nothing added</li>}</ul></div>
        </div>) : null}
    </div>
  );
}

function PointBlock({ s, b, i, openPoint, onPoint, pts }: {
  s: PwSection; b: Block; i: number; openPoint: string | null; onPoint: (id: string) => void; pts: Map<string, PvPoint>;
}) {
  const click = (id: string) => (e: React.MouseEvent) => { e.stopPropagation(); onPoint(id); };
  const txt = "text-[11.5px] leading-[1.5]";
  if (b.t === "p") {
    const id = `${s.key}:${i}`;
    return (
      <div>
        <p className={cn(txt, "cursor-pointer rounded-sm text-text-primary hover:bg-accent-muted/40", b.exempt && "text-text-muted", openPoint === id && "bg-accent-muted/50")}
           onClick={click(id)} data-testid="pw-point" data-point={id}><Rich text={b.text} /></p>
        {openPoint === id ? <EvidenceBox point={pts.get(id)} /> : null}
      </div>);
  }
  if (b.t === "bullets" || b.t === "numbered") {
    const L = b.t === "numbered" ? "ol" : "ul";
    return (
      <L className={cn("space-y-0.5 pl-5 text-text-primary", txt, b.t === "numbered" ? "list-decimal" : "list-disc")}>
        {b.items.map((x, j) => {
          const id = `${s.key}:${i}:${j}`;
          return (
            <li key={j}>
              <span className={cn("cursor-pointer rounded-sm hover:bg-accent-muted/40", openPoint === id && "bg-accent-muted/50")} onClick={click(id)}
                    data-testid="pw-point" data-point={id}><Rich text={x} /></span>
              {openPoint === id ? <EvidenceBox point={pts.get(id)} /> : null}
            </li>);
        })}
      </L>);
  }
  if (b.t === "table" || b.t === "kv") {
    const id = `${s.key}:${i}`;
    return (
      <div>
        <div className="cursor-pointer" onClick={click(id)} data-testid="pw-point" data-point={id}><BlockView b={b} dense /></div>
        {openPoint === id ? <EvidenceBox point={pts.get(id)} /> : null}
      </div>);
  }
  return <BlockView b={b} dense />;
}

function EvidenceBox({ point }: { point: PvPoint | undefined }) {
  return (
    <div className="my-1 rounded-md border border-accent/40 bg-surface-sunken p-2 text-[11px]" data-testid="pw-evidence" onClick={(e) => e.stopPropagation()}>
      {!point ? <span className="inline-flex items-center gap-1 text-text-muted"><Loader2 size={12} className="animate-spin" /> Reading the evidence…</span>
        : point.evidence.length ? (
          <ul className="space-y-1">
            {point.evidence.map((e, i) => (
              <li key={i} className="flex items-start gap-2" data-testid="pw-evidence-item" data-kind={e.kind}>
                <Chip tone={KIND_TONE[e.kind]}>{EVIDENCE_LABEL[e.kind]}</Chip>
                <span className="min-w-0 break-words text-text-secondary">{evidenceText(e)}{e.printed ? <span className="text-text-muted"> · printed {e.printed}</span> : null}</span>
              </li>))}
          </ul>)
        : <span className="text-text-muted" data-testid="pw-evidence-none">{point.has_figure ? "No source found for this figure." : "Wording of the section; no figure or record behind it."}</span>}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ versions

function VersionList({ st, viewing, onView }: { st: PwState; viewing: number | null; onView: (n: number) => void }) {
  const fv = st.workspace.final_version;
  return (
    <div className="max-h-56 overflow-y-auto border-b border-border bg-surface px-4 py-2" data-testid="pw-versions">
      <ol className="space-y-1">
        {[...st.versions].reverse().map((v) => {
          const status = v.change?.status;
          const cur = v.n === st.workspace.current_version;
          return (
            <li key={v.n} className="flex flex-wrap items-center gap-2 text-[11.5px]" data-testid="pw-version" data-version={v.n}>
              <button type="button" onClick={() => onView(v.n)} className={cn("font-medium text-accent hover:underline", (viewing === v.n || (cur && viewing == null)) && "underline")}>
                {versionLine(v, fv)}</button>
              {v.instruction ? <span className="min-w-0 truncate text-text-secondary">“{v.instruction}”</span> : <span className="text-text-muted">{v.note}</span>}
              {status ? <Chip tone={status === "pending" ? "warning" : status === "undone" ? "negative" : "positive"}>{status}</Chip> : null}
              {cur ? <Chip tone="accent">current</Chip> : null}
              <a href={fileHref(pwUrls.docx(st.workspace.ws_id, v.n))} className="text-[11px] text-accent underline" data-testid="pw-version-docx">Word</a>
            </li>);
        })}
      </ol>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ the conversation

function Conversation({ st, focus, onClearFocus, busy, onSend, error, onDismissError, applied, onAppliedDone, onShow }: {
  st: PwState; focus: PwSection | null; onClearFocus: () => void; busy: string; onSend: (t: string) => Promise<void>; error: string; onDismissError: () => void;
  applied: { turnId: string; props: Omit<AfterInstructionProps, "onDone"> } | null; onAppliedDone: () => void; onShow: (key: string) => void;
}) {
  const { settings } = useNoor();
  const name = settings?.name || "Noor";
  const [text, setText] = React.useState("");
  const list = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => { list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" }); }, [st.turns.length, busy]);
  const After = afterInstructionComponent();
  const submit = () => { const t = text; setText(""); void onSend(t); };
  const sugg = suggestions(st.workspace.kind, focus?.key ?? null, focus?.heading ?? null);
  return (
    <aside className="flex min-h-0 flex-col border-t border-border bg-surface lg:border-l lg:border-t-0" aria-label={`Ask ${name} about this document`} data-testid="pw-conversation">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <span className="text-[13px] font-semibold text-text-primary">Ask {name}</span>
        <span className="text-[11px] text-text-muted">edits this document, one section at a time</span>
        <Chip tone={st.model ? "positive" : "neutral"} title={st.model ? "A model is connected; the fixed instructions still apply by rules" : "No model key: the fixed instruction set, applied by rules"}>
          {st.model ? "Model + rules" : "Rules"}</Chip>
      </div>
      {st.rules_applied.length ? (
        <div className="border-b border-border px-3 py-1.5 text-[11px] text-text-secondary" data-testid="pw-rules-applied">
          <b>Rules applied:</b> {st.rules_applied.map((r) => r.text).join(" · ")}</div>) : null}
      <div ref={list} className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-3" data-testid="pw-turns">
        {st.turns.map((t) => (
          <React.Fragment key={t.turn_id}>
            <TurnBubble t={t} name={name} onShow={onShow} />
            {After && applied && applied.turnId === t.turn_id ? (
              <div data-testid="pw-after-instruction">{React.createElement(After as React.ComponentType<AfterInstructionProps>, { ...applied.props, onDone: onAppliedDone })}</div>) : null}
          </React.Fragment>))}
        {busy ? <p className="inline-flex items-center gap-2 text-[11.5px] text-text-muted" data-testid="pw-busy"><Loader2 size={13} className="animate-spin" /> {busy}</p> : null}
      </div>
      {error ? (
        <p role="alert" className="flex items-start gap-2 px-3 pb-1 text-[11.5px] text-negative" data-testid="pw-send-error">{error}
          <button type="button" onClick={onDismissError} aria-label="Dismiss" className="ml-auto"><X size={12} /></button></p>) : null}
      <div className="space-y-1.5 border-t border-border px-3 py-2" data-testid="pw-composer">
        {focus ? (
          <div className="flex items-center gap-1 text-[11px] text-text-secondary" data-testid="pw-focus">
            <span>Section:</span><Chip tone="accent">{sectionNo(st.paper.sections, focus.key, st.workspace.kind)} {focus.heading}</Chip>
            <button type="button" onClick={onClearFocus} aria-label="Clear the section" className="text-text-muted hover:text-text-primary"><X size={12} /></button>
          </div>) : <p className="text-[11px] text-text-muted">Click a section on the left to point {name} at it, or name it.</p>}
        <div className="flex flex-wrap gap-1" data-testid="pw-suggestions">
          {sugg.map((x) => (
            <button key={x} type="button" onClick={() => setText(x)} className="rounded-full border border-border px-2 py-0.5 text-[10.5px] text-text-secondary hover:bg-surface-hover">{x}</button>))}
        </div>
        <div className="flex items-end gap-1.5">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} placeholder="Tell Noor what to change…" aria-label="Instruction" data-testid="pw-input"
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
                    className="min-h-[44px] flex-1 resize-y rounded-md border border-border bg-surface px-2.5 py-2 text-[12.5px] text-text-primary outline-none focus:border-accent" />
          <MicButton value={text} onChange={setText} testId="pw-mic" />
          <PrimaryButton onClick={submit} disabled={!text.trim() || !!busy} aria-label="Send" data-testid="pw-send"><ArrowUp size={14} /></PrimaryButton>
        </div>
      </div>
    </aside>
  );
}

function TurnBubble({ t, name, onShow }: { t: PwTurn; name: string; onShow: (k: string) => void }) {
  const kind = String(t.meta?.kind ?? "");
  if (t.role === "user") {
    return (
      <div className="flex justify-end" data-testid="pw-turn-user">
        <div className="max-w-[88%] rounded-lg bg-accent-muted px-2.5 py-1.5 text-[12px] text-text-primary">{t.text}</div>
      </div>);
  }
  return (
    <div className="space-y-0.5" data-testid="pw-turn-noor" data-kind={kind}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">{name}</p>
      <div className={cn("rounded-lg border px-2.5 py-1.5 text-[12px] leading-[1.45] text-text-primary",
        kind === "rejected" ? "border-negative/40 bg-negative/5" : kind === "edit" || kind === "structure" ? "border-warning/40 bg-warning/5" : "border-border bg-surface-sunken")}>
        {t.text}
        {t.section && (kind === "edit" || kind === "structure") ? (
          <button type="button" className="ml-1 text-[11px] text-accent underline" onClick={() => onShow(t.section)} data-testid="pw-turn-show">Show</button>) : null}
      </div>
    </div>
  );
}
