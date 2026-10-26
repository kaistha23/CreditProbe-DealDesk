"use client";

/**
 * Lens dialogs: Save, Share (users or teams, through Mail), Add to a Playbook report, Schedule a refresh note,
 * Add ratio (the metric catalogue and the custom-ratio builder, validated by the engine), Versions.
 */

import Link from "next/link";
import * as React from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";
import { type Book, type LensDetail, type Meta, type PlaybookReport, type Version, lenses, when } from "@/lib/v5/lenses";
import { friendlyMessage } from "@/lib/v5/errors";

export function Modal({ title, onClose, children, testId, wide }: { title: string; onClose: () => void; children: React.ReactNode; testId: string; wide?: boolean }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true" aria-label={title} data-testid={testId}>
      <div className={cn("max-h-[90vh] w-full space-y-3 overflow-auto rounded-lg border border-border bg-surface p-4 shadow-lg", wide ? "max-w-2xl" : "max-w-md")}>
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-text-primary">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" data-testid={`${testId}-close`}><X size={16} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

const inputCls = "w-full rounded-md border border-border bg-surface px-2 py-1 text-[12px]";
const primary = "rounded-md bg-accent px-3 py-1 text-[12px] font-medium text-accent-contrast disabled:opacity-40";
const plain = "rounded-md border border-border px-3 py-1 text-[12px]";

function useAction<T>() {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const run = async (fn: () => Promise<T>): Promise<T | null> => {
    setBusy(true);
    setError("");
    try { return await fn(); } catch (e) { setError(friendlyMessage(e)); return null; } finally { setBusy(false); }
  };
  return { busy, error, run };
}

export function SaveDialog({ lens, onClose, onSaved }: { lens: LensDetail; onClose: () => void; onSaved: (id: string, copied: boolean) => void }) {
  const [name, setName] = React.useState(lens.name);
  const [desc, setDesc] = React.useState(lens.description);
  const [tags, setTags] = React.useState(lens.tags.join(", "));
  const a = useAction<{ lens_id: string; copied: boolean }>();
  const save = async () => {
    const out = await a.run(() => lenses.save(lens.lens_id, { name, description: desc, tags: tags.split(",").map((t) => t.trim()).filter(Boolean) }));
    if (out) onSaved(out.lens_id, out.copied);
  };
  return (
    <Modal title="Save lens" onClose={onClose} testId="lens-save-dialog">
      <label className="block space-y-1 text-[12px]"><span className="text-text-muted">Name</span>
        <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} data-testid="lens-save-name" /></label>
      <label className="block space-y-1 text-[12px]"><span className="text-text-muted">Description</span>
        <textarea className={inputCls} rows={2} value={desc} onChange={(e) => setDesc(e.target.value)} data-testid="lens-save-description" /></label>
      <label className="block space-y-1 text-[12px]"><span className="text-text-muted">Tags (comma separated)</span>
        <input className={inputCls} value={tags} onChange={(e) => setTags(e.target.value)} data-testid="lens-save-tags" /></label>
      {a.error ? <p className="text-[12px] text-negative" role="alert">{a.error}</p> : null}
      <div className="flex justify-end gap-2">
        <button type="button" className={plain} onClick={onClose}>Cancel</button>
        <button type="button" className={primary} disabled={a.busy || !name.trim()} onClick={() => void save()} data-testid="lens-save-confirm">{a.busy ? "Saving…" : "Save"}</button>
      </div>
    </Modal>
  );
}

const USERS: [string, string][] = [["faisal.alqahtani", "Faisal Al-Qahtani"], ["noura.alharbi", "Noura Al-Harbi"], ["khalid.alotaibi", "Khalid Al-Otaibi"],
  ["reem.alshehri", "Reem Al-Shehri"], ["abdullah.alzahrani", "Abdullah Al-Zahrani"], ["sara.aldosari", "Sara Al-Dosari"], ["omar.alghamdi", "Omar Al-Ghamdi"],
  ["lama.almutairi", "Lama Al-Mutairi"], ["anne", "Anne"]];
const TEAMS: [string, string][] = [["risk", "Risk"], ["corporate", "Corporate credit"], ["retail", "Retail credit"], ["validation", "Model validation"]];

export function ShareDialog({ lens, onClose }: { lens: LensDetail; onClose: () => void }) {
  const [users, setUsers] = React.useState<string[]>([]);
  const [teams, setTeams] = React.useState<string[]>([]);
  const [note, setNote] = React.useState("");
  const [done, setDone] = React.useState<string[] | null>(null);
  const a = useAction<{ shared_with: string[] }>();
  const toggle = (list: string[], set: (x: string[]) => void, v: string) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const share = async () => { const out = await a.run(() => lenses.share(lens.lens_id, { users, teams, note })); if (out) setDone(out.shared_with); };
  return (
    <Modal title="Share lens" onClose={onClose} testId="lens-share-dialog">
      {done ? <p className="text-[13px] text-positive" data-testid="lens-share-done">Shared through Mail with {done.length} {done.length === 1 ? "person" : "people"}.</p> : <>
        <div className="grid grid-cols-2 gap-1 text-[12px]">
          {USERS.filter(([u]) => u !== lens.owner).map(([u, n]) => (
            <label key={u} className="flex items-center gap-1.5"><input type="checkbox" checked={users.includes(u)} onChange={() => toggle(users, setUsers, u)}
                                                                        data-testid={`lens-share-user-${u}`} />{n}</label>))}
        </div>
        <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Teams</p>
        <div className="flex flex-wrap gap-2 text-[12px]">
          {TEAMS.map(([t, n]) => (
            <label key={t} className="flex items-center gap-1.5"><input type="checkbox" checked={teams.includes(t)} onChange={() => toggle(teams, setTeams, t)}
                                                                        data-testid={`lens-share-team-${t}`} />{n}</label>))}
        </div>
        <textarea className={inputCls} rows={2} placeholder="A note (optional)" value={note} onChange={(e) => setNote(e.target.value)} data-testid="lens-share-note" />
        {a.error ? <p className="text-[12px] text-negative" role="alert">{a.error}</p> : null}
        <div className="flex justify-end gap-2">
          <button type="button" className={plain} onClick={onClose}>Cancel</button>
          <button type="button" className={primary} disabled={a.busy || (!users.length && !teams.length)} onClick={() => void share()} data-testid="lens-share-confirm">
            {a.busy ? "Sharing…" : "Share"}</button>
        </div></>}
    </Modal>
  );
}

export function AddReportDialog({ lens, book, onClose }: { lens: LensDetail; book: Book; onClose: () => void }) {
  const [reports, setReports] = React.useState<PlaybookReport[] | null>(null);
  const [choice, setChoice] = React.useState("new");
  const [title, setTitle] = React.useState(`${lens.name}: lens report`);
  const [done, setDone] = React.useState<{ title: string; href: string } | null>(null);
  const a = useAction<{ report_title: string; href: string }>();
  React.useEffect(() => {
    let live = true;
    lenses.playbookReports().then((r) => { if (live) setReports(r.reports); }).catch(() => { if (live) setReports([]); });
    return () => { live = false; };
  }, []);
  const add = async () => {
    const out = await a.run(() => lenses.toPlaybook(lens.lens_id, choice === "new" ? { new_report: { title, book } } : { report_id: choice }));
    if (out) setDone({ title: out.report_title, href: out.href });
  };
  return (
    <Modal title="Add to a Playbook report" onClose={onClose} testId="lens-report-dialog">
      {done ? (
        <div className="space-y-2" data-testid="lens-report-done">
          <p className="text-[13px] text-positive">Added to {done.title} as a section with the lens figures.</p>
          <Link href={done.href} className="text-[12px] text-accent underline" data-testid="lens-report-open">Open the report</Link>
        </div>) : <>
        {!reports ? <p className="text-[12px] text-text-muted">Loading the reports you can edit…</p> : null}
        <div className="max-h-48 space-y-1 overflow-auto text-[12px]">
          {(reports ?? []).map((r) => (
            <label key={r.id} className="flex items-start gap-2"><input type="radio" name="report" checked={choice === r.id} onChange={() => setChoice(r.id)}
                                                                      data-testid="lens-report-existing" />
              <span>{r.title} <span className="text-text-muted">· {r.status.replace("_", " ")}</span></span></label>))}
          <label className="flex items-center gap-2"><input type="radio" name="report" checked={choice === "new"} onChange={() => setChoice("new")}
                                                            data-testid="lens-report-new" /> A new report</label>
        </div>
        {choice === "new" ? <input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} data-testid="lens-report-title" aria-label="Report title" /> : null}
        {a.error ? <p className="text-[12px] text-negative" role="alert" data-testid="lens-report-error">{a.error}</p> : null}
        <div className="flex justify-end gap-2">
          <button type="button" className={plain} onClick={onClose}>Cancel</button>
          <button type="button" className={primary} disabled={a.busy || (choice === "new" && !title.trim())} onClick={() => void add()} data-testid="lens-report-confirm">
            {a.busy ? "Adding…" : "Add"}</button>
        </div></>}
    </Modal>
  );
}

export function ScheduleDialog({ lens, onClose, onDone }: { lens: LensDetail; onClose: () => void; onDone: () => void }) {
  const [cadence, setCadence] = React.useState(lens.schedule?.cadence ?? "weekly");
  const [teams, setTeams] = React.useState<string[]>([]);
  const a = useAction<unknown>();
  const go = async (c: string) => { const out = await a.run(() => lenses.schedule(lens.lens_id, { cadence: c, teams })); if (out) { onDone(); onClose(); } };
  return (
    <Modal title="Schedule a refresh note" onClose={onClose} testId="lens-schedule-dialog">
      <p className="text-[12px] text-text-secondary">A note with the lens&rsquo;s current figures goes to you{teams.length ? " and the teams chosen" : ""} through Mail.</p>
      <div className="flex gap-2 text-[12px]">
        {["daily", "weekly", "monthly"].map((c) => (
          <label key={c} className="flex items-center gap-1"><input type="radio" name="cad" checked={cadence === c} onChange={() => setCadence(c)} data-testid={`lens-schedule-${c}`} />
            {c[0].toUpperCase() + c.slice(1)}</label>))}
      </div>
      <div className="flex flex-wrap gap-2 text-[12px]">
        {TEAMS.map(([t, n]) => (
          <label key={t} className="flex items-center gap-1"><input type="checkbox" checked={teams.includes(t)}
                                                                    onChange={() => setTeams(teams.includes(t) ? teams.filter((x) => x !== t) : [...teams, t])} />{n}</label>))}
      </div>
      {a.error ? <p className="text-[12px] text-negative" role="alert">{a.error}</p> : null}
      <div className="flex justify-end gap-2">
        {lens.schedule ? <button type="button" className={plain} onClick={() => void go("off")} data-testid="lens-schedule-off">Turn off</button> : null}
        <button type="button" className={primary} disabled={a.busy} onClick={() => void go(cadence)} data-testid="lens-schedule-confirm">Schedule</button>
      </div>
    </Modal>
  );
}

export function AddRatioDialog({ meta, book, onClose, onAdd }: { meta: Meta; book: Book; onClose: () => void; onAdd: (op: Record<string, unknown>) => void }) {
  const [q, setQ] = React.useState("");
  const [tab, setTab] = React.useState<"catalogue" | "custom">("catalogue");
  const [num, setNum] = React.useState("stage2_ead");
  const [den, setDen] = React.useState("ead");
  const [label, setLabel] = React.useState("Custom ratio");
  const [fdim, setFdim] = React.useState("");
  const [fval, setFval] = React.useState("");
  const [check, setCheck] = React.useState<string>("");
  const a = useAction<{ display: string; period: string }>();
  const additive = meta.metrics.filter((m) => m.kind === "sum" || m.kind === "distinct");
  const filters = fdim && fval ? [{ dim: fdim, values: [fval] }] : [];
  const groups = Array.from(new Set(meta.metrics.map((m) => m.group)));
  const shown = meta.metrics.filter((m) => !q || `${m.label} ${m.source} ${m.group}`.toLowerCase().includes(q.toLowerCase()));
  const validate = async () => {
    const out = await a.run(() => lenses.validateRatio({ book, num, den, filters, label }));
    if (out) setCheck(`${out.display} on the whole book at ${out.period}`);
  };
  return (
    <Modal title="Add ratio" onClose={onClose} testId="lens-ratio-dialog" wide>
      <div className="flex gap-1 text-[12px]">
        {(["catalogue", "custom"] as const).map((t) => (
          <button key={t} type="button" onClick={() => setTab(t)} data-testid={`lens-ratio-tab-${t}`}
                  className={cn("rounded px-2.5 py-1", tab === t ? "bg-accent text-accent-contrast" : "border border-border")}>{t === "catalogue" ? "Metric catalogue" : "Custom ratio"}</button>))}
      </div>
      {tab === "catalogue" ? <>
        <input className={inputCls} placeholder="Search metrics across all modules" value={q} onChange={(e) => setQ(e.target.value)}
               data-testid="lens-ratio-search" />
        <div className="max-h-[50vh] space-y-3 overflow-auto">
          {groups.map((g) => {
            const ms = shown.filter((m) => m.group === g);
            if (!ms.length) return null;
            return (
              <div key={g} className="space-y-1">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">{g}</p>
                {ms.map((m) => (
                  <div key={m.key} className="flex items-center justify-between gap-2 rounded border border-border/60 px-2 py-1 text-[12px]">
                    <span className="min-w-0"><span className="text-text-primary">{m.label}</span> <span className="text-text-muted">· {m.source}{m.description ? ` · ${m.description}` : ""}</span></span>
                    <span className="flex shrink-0 gap-1">
                      <button type="button" className={plain} data-testid={`lens-ratio-trend-${m.key}`}
                              onClick={() => { onAdd({ op: "add", tile: { type: "trend", metrics: [m.key] } }); onClose(); }}>Trend</button>
                      {!["scorecard", "dealdesk"].includes(m.kind) ? (
                        <button type="button" className={plain} data-testid={`lens-ratio-kpi-${m.key}`}
                                onClick={() => { onAdd({ op: "add", tile: { type: "breakdown", metric: m.key, dim: book === "corporate" ? "sector" : "product" } }); onClose(); }}>
                          By {book === "corporate" ? "sector" : "product"}</button>) : null}
                    </span>
                  </div>))}
              </div>);
          })}
        </div></> : (
        <div className="space-y-2 text-[12px]">
          <label className="block space-y-1"><span className="text-text-muted">Name</span><input className={inputCls} value={label} onChange={(e) => setLabel(e.target.value)} data-testid="lens-ratio-label" /></label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block space-y-1"><span className="text-text-muted">Numerator</span>
              <select className={inputCls} value={num} onChange={(e) => setNum(e.target.value)} data-testid="lens-ratio-num">
                {additive.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}</select></label>
            <label className="block space-y-1"><span className="text-text-muted">Denominator</span>
              <select className={inputCls} value={den} onChange={(e) => setDen(e.target.value)} data-testid="lens-ratio-den">
                {additive.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}</select></label>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="block space-y-1"><span className="text-text-muted">Numerator filter</span>
              <select className={inputCls} value={fdim} onChange={(e) => { setFdim(e.target.value); setFval(""); }} data-testid="lens-ratio-filter-dim">
                <option value="">None</option>
                {Object.keys(meta.values).map((d) => <option key={d} value={d}>{meta.dimensions.find((x) => x.key === d)?.label ?? d}</option>)}</select></label>
            <label className="block space-y-1"><span className="text-text-muted">Value</span>
              <select className={inputCls} value={fval} onChange={(e) => setFval(e.target.value)} disabled={!fdim} data-testid="lens-ratio-filter-value">
                <option value="">Choose…</option>
                {(meta.values[fdim] ?? []).map((v) => <option key={v} value={v}>{v}</option>)}</select></label>
          </div>
          {check ? <p className="text-positive" data-testid="lens-ratio-valid">Valid: {check}</p> : null}
          {a.error ? <p className="text-negative" role="alert" data-testid="lens-ratio-error">{a.error}</p> : null}
          <div className="flex justify-end gap-2">
            <button type="button" className={plain} onClick={() => void validate()} disabled={a.busy} data-testid="lens-ratio-validate">Validate</button>
            <button type="button" className={primary} disabled={!check} data-testid="lens-ratio-add"
                    onClick={() => { onAdd({ op: "custom_ratio", label, num, den, filters }); onClose(); }}>Add to lens</button>
          </div>
        </div>)}
    </Modal>
  );
}

export function VersionsDialog({ versions, head, canEdit, onRestore, onClose }: { versions: Version[]; head: number; canEdit: boolean;
  onRestore: (v: number) => void; onClose: () => void }) {
  return (
    <Modal title="Versions" onClose={onClose} testId="lens-versions-dialog">
      <ol className="max-h-[60vh] space-y-1 overflow-auto text-[12px]">
        {[...versions].reverse().map((v) => (
          <li key={v.version} className={cn("flex items-start justify-between gap-2 rounded border px-2 py-1", v.version === head ? "border-accent" : "border-border/60")}
              data-testid="lens-version">
            <span><b>v{v.version}</b> · {v.change || "Edit"} <span className="text-text-muted">· {v.author || "CreditProbe"} · {when(v.created_at)}</span></span>
            {canEdit && v.version !== head ? <button type="button" className={plain} onClick={() => onRestore(v.version)} data-testid={`lens-restore-${v.version}`}>Restore</button>
              : v.version === head ? <span className="text-[11px] text-accent">Current</span> : null}
          </li>))}
      </ol>
    </Modal>
  );
}
