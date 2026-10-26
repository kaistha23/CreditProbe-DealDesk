"use client";

/**
 * One lens (PLAN_R5 L1.2-L1.5; R13 L layout: the reading on top, a compact KPI strip, then the chart grid):
 * breadcrumbs and Back to Lenses, the as-of period, the interpretation, the KPI strip,
 * 8-14 Plotly tiles and the top-names table, each with its trace (i) and (⋯) menu; undo/redo and versions; Save,
 * Share, Add to report, Export (house-style Excel/PDF), Schedule; and the assistant panel on the right (the lens's
 * thread, collapsible). State is in the URL: /lenses/<id>?period=<p>&panel=0.
 */

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BackButton } from "@/components/v5/core/back-button";
import * as React from "react";
import { ChevronRight, Clock, Copy, Download, FilePlus2, History, MessageSquare, PanelRightClose, Plus, Redo2, Save, Share2, Undo2 } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AnswerMarkdown } from "@/components/v5/thread";
import { cn } from "@/lib/utils";
import { BOOK_WORD, type LensDetail, type Meta, type Rendered, lenses } from "@/lib/v5/lenses";
import { CrmFindings } from "./crm";
import { MonitoringAgentButton, monitorScopeOf, monitorTabOf } from "./monitoring";

import { KpiStrip, LensInterpretation } from "./dashboard";
import { type AddTarget, LensAssistant } from "./assistant";
import { dashboardLines } from "./assistant-model"; // R14 G: the assistant does not repeat the interpretation
import { AddRatioDialog, AddReportDialog, SaveDialog, ScheduleDialog, ShareDialog, VersionsDialog } from "./dialogs";
import { TileCard } from "./tile";
import { friendlyMessage } from "@/lib/v5/errors";
import { threadViewKey } from "@/lib/v5/thread-rule";

type Dialog = "" | "save" | "share" | "report" | "schedule" | "ratio" | "versions";

const tool = "inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[12px] text-text-primary hover:bg-surface-hover disabled:opacity-40";

export function LensView({ lensId }: { lensId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const period = params.get("period") ?? "";
  const panel = params.get("panel") !== "0";
  const [lens, setLens] = React.useState<LensDetail | null>(null);
  const [view, setView] = React.useState<Rendered | null>(null);
  const [meta, setMeta] = React.useState<Meta | null>(null);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [dialog, setDialog] = React.useState<Dialog>("");
  const [seed, setSeed] = React.useState<{ text: string; nonce: number } | null>(null);

  const setParam = React.useCallback((k: string, v: string) => {
    const p = new URLSearchParams(params.toString());
    if (v) p.set(k, v); else p.delete(k);
    router.replace(`${pathname}${p.toString() ? `?${p}` : ""}`);
  }, [params, pathname, router]);

  const reload = React.useCallback(async () => {
    try {
      const [l, r] = await Promise.all([lenses.lens(lensId), lenses.render(lensId, period)]);
      setLens(l);
      setView(r);
      setError("");
      if (!meta || meta.book !== l.book) setMeta(await lenses.meta(l.book));
    } catch (e) { setError(friendlyMessage(e)); }
  }, [lensId, period, meta]);

  React.useEffect(() => { void Promise.resolve().then(reload); }, [lensId, period]); // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (fn: () => Promise<{ change?: string } | unknown>, message?: string) => {
    setBusy(true);
    setNotice("");
    try { const out = await fn() as { change?: string }; await reload(); setNotice(message ?? (out?.change ? `${out.change}.` : "")); }
    catch (e) { setNotice(friendlyMessage(e)); }
    finally { setBusy(false); }
  };
  const onOp = (op: Record<string, unknown>) => void act(() => lenses.edit(lensId, op));
  const addTarget: AddTarget = {
    tiles: (view?.tiles ?? []).map((t) => ({ id: t.id, title: t.title })),
    onAdd: async ({ block, sql, question, after }) => {
      setBusy(true);
      setNotice("");
      try { await lenses.edit(lensId, { op: "add_block", block, sql, question, after }); await reload(); setNotice("Added to the lens from the assistant."); return true; }
      catch (e) { setNotice(friendlyMessage(e)); return false; }
      finally { setBusy(false); }
    },
    onUndo: () => act(() => lenses.undo(lensId), "Undone."),
  };
  const onHandoff = async (tileId: string, target: "cockpit" | "whatif") => {
    try { const out = await lenses.handoff(lensId, tileId, target); router.push(out.href); }
    catch (e) { setNotice(friendlyMessage(e)); }
  };
  const askAssistant = (text: string) => { if (!panel) setParam("panel", ""); setSeed({ text, nonce: Date.now() }); };

  if (error) return (
    <div className="space-y-3" data-testid="lens-error">
      <BackButton fallback={{ href: "/lenses", label: "Lenses" }} testId="lens-back" />
      <p className="text-[13px] text-negative" role="alert">{error}</p>
    </div>);
  if (!lens || !view) return <div className="space-y-3" data-testid="lens-loading"><Skeleton className="h-10 w-1/2" /><Skeleton className="h-24 w-full" /><Skeleton className="h-72 w-full" /></div>;

  const specById = Object.fromEntries(lens.spec.tiles.map((t) => [t.id, t]));
  const canEdit = lens.can_edit;

  return (
    <div className="space-y-4" data-testid="lens-view" data-lens={lens.lens_id} data-version={view.version} data-charts={view.charts} data-untraced={view.untraced}>
      <BackButton fallback={{ href: lens.book === "retail" ? "/lenses?book=retail" : "/lenses", label: "Lenses" }} testId="lens-back" />
      <nav className="flex items-center gap-1 text-[12px] text-text-muted" aria-label="Breadcrumbs" data-testid="lens-breadcrumbs">
        <Link href="/lenses" className="hover:text-accent" data-testid="lens-crumb-home">Lenses</Link><ChevronRight size={12} />
        <Link href={lens.book === "retail" ? "/lenses?book=retail" : "/lenses"} className="hover:text-accent">{BOOK_WORD[lens.book]}</Link><ChevronRight size={12} />
        <span className="truncate text-text-primary">{lens.name}</span>
      </nav>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Lens · {BOOK_WORD[lens.book]}{lens.kind === "template" ? " · Template" : !lens.saved ? " · Draft" : ""}</p>
          <h1 className="truncate text-2xl font-semibold text-text-primary" data-testid="lens-title">{lens.name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-1.5" data-testid="lens-scope">
            {view.scope.length ? view.scope.map((s) => (
              <span key={s.dim} className="rounded-full border border-border px-2 py-0.5 text-[11px] text-text-secondary">{s.label}: {s.values.join(", ")}</span>))
              : <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-text-secondary">Whole {lens.book} book</span>}
            {view.compare ? <span className="rounded-full border border-accent px-2 py-0.5 text-[11px] text-accent">Compared with {view.compare.label}</span> : null}
          </div>
        </div>
        <label className="flex items-center gap-1.5 text-[12px] text-text-muted">As of
          <select value={view.period} onChange={(e) => setParam("period", e.target.value === view.periods[view.periods.length - 1] ? "" : e.target.value)}
                  data-testid="lens-period" className="rounded-md border border-border bg-surface px-2 py-1 text-[12px] text-text-primary">
            {[...view.periods].reverse().map((p) => <option key={p} value={p}>{p}</option>)}
          </select></label>
      </div>

      <div className="flex flex-wrap items-center gap-1.5" data-testid="lens-toolbar">
        <button type="button" className={tool} disabled={!canEdit || busy || lens.head <= 1} onClick={() => void act(() => lenses.undo(lensId), "Undone.")} data-testid="lens-undo"><Undo2 size={13} /> Undo</button>
        <button type="button" className={tool} disabled={!canEdit || busy || lens.head >= lens.latest} onClick={() => void act(() => lenses.redo(lensId), "Redone.")} data-testid="lens-redo"><Redo2 size={13} /> Redo</button>
        <button type="button" className={tool} onClick={() => setDialog("versions")} data-testid="lens-versions"><History size={13} /> Versions ({lens.latest})</button>
        <span className="mx-1 h-5 w-px bg-border" />
        <button type="button" className={tool} disabled={!canEdit || busy} onClick={() => setDialog("ratio")} data-testid="lens-add-ratio"><Plus size={13} /> Add ratio</button>
        <span className="mx-1 h-5 w-px bg-border" />
        <button type="button" className={tool} onClick={() => setDialog("share")} data-testid="lens-share"><Share2 size={13} /> Share</button>
        <button type="button" className={tool} onClick={() => setDialog("report")} data-testid="lens-add-report"><FilePlus2 size={13} /> Add to report</button>
        <a className={tool} href={lenses.exportUrl(lensId, "xlsx", period)} data-testid="lens-export-xlsx"><Download size={13} /> Excel</a>
        <a className={tool} href={lenses.exportUrl(lensId, "pdf", period)} data-testid="lens-export-pdf"><Download size={13} /> PDF</a>
        <button type="button" className={tool} onClick={() => setDialog("schedule")} data-testid="lens-schedule" disabled={lens.kind === "template"}>
          <Clock size={13} /> {lens.schedule ? `Refresh note: ${lens.schedule.cadence}` : "Schedule"}</button>
        <MonitoringAgentButton className={tool} scope={monitorScopeOf(lens)} initialTab={monitorTabOf(params.get("monitor"))} currentLens={lens.lens_id} />
        {!canEdit ? <button type="button" className={tool} onClick={() => void lenses.duplicate(lensId).then((o) => router.push(`/lenses/${o.lens_id}`))} data-testid="lens-duplicate"><Copy size={13} /> Duplicate</button> : null}
        <button type="button" onClick={() => setDialog("save")} data-testid="lens-save"
                className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1 text-[12px] font-medium text-accent-contrast"><Save size={13} /> {lens.saved && canEdit ? "Saved" : "Save"}</button>
        <button type="button" className={cn(tool, "ml-auto")} onClick={() => setParam("panel", panel ? "0" : "")} data-testid="lens-toggle-assistant">
          {panel ? <><PanelRightClose size={13} /> Hide assistant</> : <><MessageSquare size={13} /> Assistant</>}</button>
      </div>
      {notice ? <p className="text-[12px] text-text-secondary" role="status" data-testid="lens-notice">{notice}</p> : null}

      <div className={cn("grid gap-4", panel ? "xl:grid-cols-[minmax(0,1fr)_380px]" : "")}>
        <div className="min-w-0 space-y-3">
          {view.interpretation ? <LensInterpretation it={view.interpretation} />
            : view.commentary.markdown ? (
              <Card className="px-4 py-3 text-[13px] leading-relaxed text-text-secondary" data-testid="lens-commentary">
                <AnswerMarkdown text={view.commentary.markdown} />
              </Card>) : null}
          <KpiStrip kpis={view.kpis} panelOpen={panel} />
          {view.intel?.findings?.length ? <CrmFindings findings={view.intel.findings} /> : null}

          <div className={cn("grid gap-3", panel ? "min-[1400px]:grid-cols-2" : "lg:grid-cols-2")} data-testid="lens-tiles">
            {view.tiles.map((t) => (
              <TileCard key={t.id} tile={t} spec={specById[t.id]} meta={meta} canEdit={canEdit} onOp={onOp} onAsk={askAssistant}
                        onHandoff={(id, target) => void onHandoff(id, target)} book={view.book} />))}
          </div>
        </div>
        {panel ? (
          <aside className="min-w-0 xl:sticky xl:top-4 xl:max-h-[calc(100vh-6rem)] xl:overflow-auto" data-testid="lens-assistant-panel">
            <Card className="p-3">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-text-muted">Lens assistant</p>
              {lens.thread_id ? <LensAssistant key={threadViewKey("lens-thread", lens.thread_id)} threadId={lens.thread_id} canEdit={canEdit} onLensChanged={() => void reload()} seed={seed} addTarget={addTarget} lensId={lens.lens_id}
                                                dashboard={dashboardLines(view.interpretation)} />
                : <p className="text-[12px] text-text-muted">This lens has no conversation yet.</p>}
            </Card>
          </aside>) : null}
      </div>

      {dialog === "save" ? <SaveDialog lens={lens} onClose={() => setDialog("")} onSaved={(id, copied) => {
        setDialog("");
        if (copied) router.push(`/lenses/${id}`); else void reload().then(() => setNotice("Saved."));
      }} /> : null}
      {dialog === "share" ? <ShareDialog lens={lens} onClose={() => setDialog("")} /> : null}
      {dialog === "report" ? <AddReportDialog lens={lens} book={lens.book} onClose={() => setDialog("")} /> : null}
      {dialog === "schedule" ? <ScheduleDialog lens={lens} onClose={() => setDialog("")} onDone={() => void reload().then(() => setNotice("Refresh note scheduled."))} /> : null}
      {dialog === "ratio" && meta ? <AddRatioDialog meta={meta} book={lens.book} onClose={() => setDialog("")} onAdd={onOp} /> : null}
      {dialog === "versions" ? <VersionsDialog versions={lens.versions} head={lens.head} canEdit={canEdit} onClose={() => setDialog("")}
                                               onRestore={(v) => { setDialog(""); void act(() => lenses.restore(lensId, v), `Restored version ${v}.`); }} /> : null}
    </div>
  );
}
