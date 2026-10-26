"use client";

/**
 * BRF studio as chat + flowchart (PLAN_R10 Session B, item 13, img12).
 *
 * Above the fold: one chat box (attach a template, "complete all data for this template", edit by chat) and the
 * React Flow canvas: sources → filters and joins → calculations → checks → output lines. Users add, remove and
 * re-wire nodes; every structural edit re-evaluates on the books and the values on the nodes update.
 * Lock → Run → Publish sit in the header; the populated return opens under the canvas after Run.
 */
import * as React from "react";
import { useSearchParams } from "next/navigation";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import { FileDown, FileSpreadsheet, LayoutGrid, Lock, Paperclip, Play, Plus, Send, Trash2, X } from "lucide-react";

import { InfoPopover } from "@/components/ui/info-popover";
import { AnswerProse } from "@/components/answer";
import { Pill, PoweredTrace, Rich, STATUS_TONE } from "@/components/v5/queries/parts";
import { ErrorBox, PageTop } from "@/components/v5/workspace/parts";
import {
  type BrfGraph, type BrfKind, type BrfNode, type Evaluation, type NodeValue, type QuickInfo,
  DATASET_OPTIONS, NODE_W, addNode, connect, counts, defaultNode, describe, keepPositions, layout, removeEdges, removeNodes,
  stripPositions, studio, updateNode,
} from "@/lib/v5/brf-studio";
import { cn } from "@/lib/utils";

const BTN = "inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-[12px] text-text-secondary hover:bg-surface-hover disabled:opacity-50";
const PRIMARY = "inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-3 text-[12px] font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50";
const COMPLETE = "complete all data for this template";

/** Flow colours: sources blue → transformations purple → calculations amber → checks red → outputs green. */
export const KIND: Record<BrfKind, { label: string; add: string; cls: string; dot: string }> = {
  source: { label: "Sources", add: "Source", cls: "border-l-sky-500", dot: "bg-sky-500" },
  transform: { label: "Filters and joins", add: "Filter", cls: "border-l-violet-500", dot: "bg-violet-500" },
  calc: { label: "Calculations", add: "Calculation", cls: "border-l-amber-500", dot: "bg-amber-500" },
  check: { label: "Checks", add: "Check", cls: "border-l-rose-500", dot: "bg-rose-500" },
  output: { label: "Output lines", add: "Output", cls: "border-l-emerald-500", dot: "bg-emerald-500" },
};
const KINDS: BrfKind[] = ["source", "transform", "calc", "check", "output"];
type State = "Draft" | "Locked" | "Run" | "Published";
interface Msg { who: "you" | "studio"; text: string; file?: string }

export function BrfStudio() {
  return (
    <ReactFlowProvider>
      <Studio />
    </ReactFlowProvider>
  );
}

function Studio() {
  const params = useSearchParams();
  const [info, setInfo] = React.useState<QuickInfo | null>(null);
  const [graph, setGraph] = React.useState<BrfGraph>({ nodes: [], edges: [] });
  const [template, setTemplate] = React.useState<string[]>([]);
  const [title, setTitle] = React.useState("BRF return");
  const [period, setPeriod] = React.useState("");
  const [state, setState] = React.useState<State>("Draft");
  const [ev, setEv] = React.useState<Evaluation | null>(null);
  const [run, setRun] = React.useState<Evaluation | null>(null);
  const [thread, setThread] = React.useState<Msg[]>([]);
  const [text, setText] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const [selected, setSelected] = React.useState<string[]>([]);
  const [selEdges, setSelEdges] = React.useState<string[]>([]);
  const [structure, setStructure] = React.useState(0);
  const [built, setBuilt] = React.useState(0);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const threadRef = React.useRef<HTMLDivElement>(null);
  const { fitView } = useReactFlow();

  React.useEffect(() => {
    studio.quick().then((q) => { setInfo(q); setPeriod((p) => p || q.as_of); }).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  React.useEffect(() => { threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight }); }, [thread]);
  React.useEffect(() => { if (built) setTimeout(() => fitView({ padding: 0.06, duration: 250, minZoom: 0.8, maxZoom: 1.1 }), 30); }, [built, fitView]);

  // every structural edit recomputes on the books (debounced)
  React.useEffect(() => {
    if (!structure || !period) return;
    const t = setTimeout(() => {
      if (!graph.nodes.length) { setEv(null); return; }
      studio.evaluate(graph, period).then(setEv).catch((e) => setError(e instanceof Error ? e.message : String(e)));
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structure, period]);

  const edit = (g: BrfGraph) => {
    setGraph(g);
    setStructure((s) => s + 1);
    setRun(null);
    if (state !== "Draft") setState("Draft");
  };

  const doRun = async (p = period) => {
    if (!graph.nodes.length) return;
    setBusy("run"); setError("");
    try {
      const out = await studio.evaluate(graph, p);
      setRun(out); setEv(out); setState("Run");
      setThread((t) => [...t, { who: "studio", text: `Run for **${out.period}**: ${out.summary}` }]);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); }
  };
  const doLock = (p = period) => { setPeriod(p); setState("Locked"); setRun(null); setStructure((s) => s + 1); };
  const doPublish = async () => {
    setBusy("publish"); setError("");
    try {
      const out = await studio.publish(title, graph, period);
      setState("Published");
      setThread((t) => [...t, { who: "studio", text: `Published **${title}** for **${period}**: ${out.lines} lines, ${out.checks_pass} of ${out.checks} checks pass.` }]);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); }
  };

  const doExport = async () => {
    try {
      const blob = await studio.exportXlsx(title, graph, period);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${title.replace(/[^A-Za-z0-9_-]+/g, "_")}_${period}.xlsx`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };

  const send = async (message: string, attach: File | null = file) => {
    const msg = message.trim() || (attach ? COMPLETE : "");
    if (!msg) return;
    setThread((t) => [...t, { who: "you", text: msg, file: attach?.name }]);
    setText(""); setFile(null); setBusy("chat"); setError("");
    try {
      const r = await studio.chat(msg, graph, template, period, attach);
      setTemplate(r.template);
      if (r.action === "build") {
        setGraph(layout(r.graph)); setBuilt((b) => b + 1); setRun(null); setState("Draft"); setSelected([]);
        const q = /\b(R[1-4])\b/i.exec(msg)?.[1]?.toUpperCase();
        setTitle(q ? info?.quick.find((x) => x.id === q)?.title ?? title : (attach?.name ?? r.file ?? title).replace(/\.(xlsx|xlsm|csv|txt)$/i, "").replace(/[_-]+/g, " "));
      } else if (r.action === "edit") {
        setGraph(keepPositions(r.graph, graph)); setRun(null); if (state !== "Draft") setState("Draft");
      }
      if (r.evaluation) setEv(r.evaluation);
      setThread((t) => [...t, { who: "studio", text: r.reply }]);
      if (r.action === "lock") doLock(r.period);
      if (r.action === "run") { if (state === "Draft") doLock(period); await doRun(r.period || period); }
      if (r.action === "publish") { if (state === "Run") await doPublish(); else setThread((t) => [...t, { who: "studio", text: "Lock and Run the return before publishing it." }]); }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(""); }
  };

  const openSeeded = async (name: string) => {
    try {
      const blob = await (await fetch(studio.templateUrl(name), { credentials: "include" })).blob();
      await send(COMPLETE, new File([blob], name));
    } catch { setError("Could not open that template."); }
  };

  // deep link from the earlier BRF screen: /brf?r=R1 opens that quick start
  const opened = React.useRef(false);
  React.useEffect(() => {
    const r = params.get("r");
    if (info && r && /^R[1-4]$/.test(r) && !opened.current) { opened.current = true; void send(`open quick start ${r}`, null); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info, params]);

  // ------------------------------------------------------------------ canvas wiring
  const rfNodes: Node[] = React.useMemo(() => graph.nodes.map((n) => ({
    id: n.id, type: "brf", position: n.position ?? { x: 0, y: 0 }, selected: selected.includes(n.id),
    data: { n, v: ev?.values[n.id] },
  })), [graph, ev, selected]);
  const rfEdges: Edge[] = React.useMemo(() => graph.edges.map((e) => ({
    id: e.id, source: e.source, target: e.target, selected: selEdges.includes(e.id),
    style: { stroke: selEdges.includes(e.id) ? "var(--color-accent, #8a6d3b)" : "#a8a29e", strokeWidth: selEdges.includes(e.id) ? 2 : 1.2 },
  })), [graph, selEdges]);

  const onNodesChange = (changes: NodeChange[]) => {
    let g = graph; let structural = false; let sel = selected;
    for (const c of changes) {
      if (c.type === "position" && c.position) g = { ...g, nodes: g.nodes.map((n) => (n.id === c.id ? { ...n, position: c.position } : n)) };
      else if (c.type === "remove") { g = removeNodes(g, [c.id]); structural = true; sel = sel.filter((s) => s !== c.id); }
      else if (c.type === "select") sel = c.selected ? Array.from(new Set([...sel, c.id])) : sel.filter((s) => s !== c.id);
    }
    if (sel !== selected) setSelected(sel);
    if (structural) edit(g); else if (g !== graph) setGraph(g);
  };
  const onEdgesChange = (changes: EdgeChange[]) => {
    let g = graph; let structural = false; let sel = selEdges;
    for (const c of changes) {
      if (c.type === "remove") { g = removeEdges(g, [c.id]); structural = true; sel = sel.filter((s) => s !== c.id); }
      else if (c.type === "select") sel = c.selected ? Array.from(new Set([...sel, c.id])) : sel.filter((s) => s !== c.id);
    }
    if (sel !== selEdges) setSelEdges(sel);
    if (structural) edit(g);
  };
  const onConnect = (c: Connection) => { if (c.source && c.target) edit(connect(graph, c.source, c.target)); };

  const add = (k: BrfKind) => {
    const xs = graph.nodes.map((n) => n.position?.x ?? 0);
    const n = defaultNode(k, graph, { x: (xs.length ? Math.max(...xs) : 0) + NODE_W + 60, y: 20 + graph.nodes.filter((x) => (x.position?.x ?? 0) > Math.max(0, ...xs)).length * 70 });
    edit(addNode(graph, n));
    setSelected([n.id]);
  };
  const deleteSelected = () => {
    let g = graph;
    if (selected.length) g = removeNodes(g, selected);
    if (selEdges.length) g = removeEdges(g, selEdges);
    setSelected([]); setSelEdges([]);
    edit(g);
  };

  const sel = selected.length === 1 ? graph.nodes.find((n) => n.id === selected[0]) ?? null : null;
  const c = counts(graph);
  const hasGraph = graph.nodes.length > 0;

  return (
    <div className="flex flex-col gap-3" data-testid="brf-studio" data-tour="brf-home">
      <PageTop eyebrow="Intelligence" title="BRF studio" back={{ href: "/", label: "Cockpit" }}
        about={<p>Attach a BRF template in the chat and ask CreditProbe to complete all data for it. It reads the template&apos;s lines, maps each to the Data Domains and draws the flow: sources → filters and joins → calculations → checks → output lines. Add, remove or re-wire nodes in the flow or by chat; the values recompute on the books. Then Lock the period, Run and Publish. Powered by P7.</p>}
        actions={hasGraph ? <>
          <Pill tone={STATUS_TONE[state]}>{state}</Pill>
          <select value={period} onChange={(e) => { setPeriod(e.target.value); setState("Draft"); setRun(null); setStructure((s) => s + 1); }}
                  className="h-8 rounded-md border border-border bg-surface px-2 text-[12px]" data-testid="brf-period" aria-label="Period">
            {(info?.periods ?? []).map((p) => <option key={p}>{p}</option>)}
          </select>
          <button type="button" className={BTN} disabled={!!busy || state !== "Draft"} onClick={() => doLock()} data-testid="brf-lock"><Lock size={14} aria-hidden /> Lock</button>
          <button type="button" className={PRIMARY} disabled={!!busy || state === "Draft"} onClick={() => void doRun()} data-testid="brf-run"><Play size={14} aria-hidden /> {busy === "run" ? "Running…" : "Run"}</button>
          <button type="button" className={BTN} disabled={!!busy || state !== "Run"} onClick={() => void doPublish()} data-testid="brf-publish"><Send size={14} aria-hidden /> Publish</button>
        </> : null} />
      {error ? <ErrorBox error={error} /> : null}

      {/* ------------------------------------------------------------ chat */}
      <section className="rounded-xl border border-border bg-surface p-3" data-testid="brf-chat">
        {thread.length ? (
          <div ref={threadRef} className="mb-2 max-h-[92px] space-y-1.5 overflow-y-auto pr-1 text-[13px]" data-testid="brf-thread">
            {thread.map((m, i) => (
              <div key={i} className={cn("w-fit max-w-[85%] break-words rounded-lg px-3 py-1.5", m.who === "you" ? "ml-auto bg-accent/10" : "bg-surface-hover")} data-testid={`brf-msg-${m.who}`}>
                {m.file ? <div className="mb-0.5 flex items-center gap-1 text-[11px] text-text-muted"><FileSpreadsheet size={12} aria-hidden /> {m.file}</div> : null}
                {/* PLAN_R12 N2: the assistant's replies in the shared answer style; the user's own words as typed. */}
                {m.who === "you" ? <Rich text={m.text} className="text-[13px]" /> : <AnswerProse text={m.text} compact fold={false} testId="brf-answer" />}
              </div>
            ))}
            {busy === "chat" ? <div className="w-fit rounded-lg bg-surface-hover px-3 py-1.5 text-text-muted">Reading the domains…</div> : null}
          </div>
        ) : null}
        <form className="flex items-center gap-2 rounded-lg border border-border bg-surface px-2 py-1 focus-within:border-accent" onSubmit={(e) => { e.preventDefault(); void send(text); }}>
          <input ref={fileRef} type="file" accept=".xlsx,.xlsm,.csv,.txt" className="hidden" data-testid="brf-file"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); if (!text.trim()) setText(COMPLETE); } e.target.value = ""; }} />
          <button type="button" onClick={() => fileRef.current?.click()} className="rounded p-1.5 text-text-muted hover:bg-surface-hover hover:text-text-primary" aria-label="Attach a BRF template" title="Attach a BRF template" data-testid="brf-attach"><Paperclip size={16} /></button>
          {file ? (
            <span className="inline-flex max-w-[220px] shrink-0 items-center gap-1 rounded bg-surface-hover px-2 py-0.5 text-[11px]" data-testid="brf-attached">
              <FileSpreadsheet size={12} aria-hidden /><span className="truncate">{file.name}</span>
              <button type="button" onClick={() => setFile(null)} aria-label="Remove attachment"><X size={12} /></button>
            </span>
          ) : null}
          <input value={text} onChange={(e) => setText(e.target.value)} disabled={busy === "chat"}
                 placeholder={hasGraph ? "Edit by chat, e.g. “add a reconciliation to the GL”" : "Attach a BRF template, then say “complete all data”"}
                 className="h-9 min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-text-muted" data-testid="brf-say" />
          <button type="submit" className={cn(PRIMARY, "shrink-0")} disabled={busy === "chat" || (!text.trim() && !file)} data-testid="brf-say-send"><Send size={14} aria-hidden /> Send</button>
        </form>
        <div className="mt-2 flex items-center gap-1.5 overflow-x-auto whitespace-nowrap text-[12px]" data-testid="brf-quick">
          <span className="text-text-muted">Quick start</span>
          {(info?.templates ?? []).map((t) => (
            <button key={t} type="button" disabled={!!busy} onClick={() => void openSeeded(t)} className="inline-flex shrink-0 items-center gap-1 rounded-full border border-border px-2.5 py-0.5 hover:border-accent" data-testid="brf-template-chip">
              <FileSpreadsheet size={12} aria-hidden /> {t.replace(/\.xlsx$/, "").replace(/_/g, " ")}
            </button>
          ))}
          {(info?.quick ?? []).map((q) => (
            <button key={q.id} type="button" disabled={!!busy} onClick={() => void send(`open quick start ${q.id}`, null)} className="max-w-[230px] shrink-0 truncate rounded-full border border-border px-2.5 py-0.5 hover:border-accent" title={q.title} data-testid={`brf-quick-${q.id}`}>
              {q.id} · {q.title}
            </button>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------------ flowchart */}
      <section className="flex shrink-0 flex-col overflow-hidden rounded-xl border border-border bg-surface" style={{ height: "max(640px, calc(100vh - 230px))" }} data-testid="brf-flow">
        {hasGraph ? (
          <div className="flex items-center justify-between gap-2 border-b border-border px-2 py-1">
            <div className="flex shrink-0 items-center gap-1 text-[12px]" data-testid="brf-toolbar">
              <span className="px-1 text-text-muted"><Plus size={12} className="inline" aria-hidden /> Add</span>
              {KINDS.map((k) => (
                <button key={k} type="button" onClick={() => add(k)} className="inline-flex items-center gap-1 rounded px-2 py-0.5 hover:bg-surface-hover" data-testid={`brf-add-${k}`}>
                  <span className={cn("h-2 w-2 rounded-full", KIND[k].dot)} /> {KIND[k].add}
                </button>
              ))}
              <span className="mx-1 h-4 w-px bg-border" />
              <button type="button" onClick={deleteSelected} disabled={!selected.length && !selEdges.length} className="inline-flex items-center gap-1 rounded px-2 py-0.5 hover:bg-surface-hover disabled:opacity-40" data-testid="brf-delete"><Trash2 size={12} aria-hidden /> Delete</button>
              <button type="button" onClick={() => { setGraph(layout(stripPositions(graph))); setBuilt((b) => b + 1); }} className="inline-flex items-center gap-1 rounded px-2 py-0.5 hover:bg-surface-hover" data-testid="brf-relayout"><LayoutGrid size={12} aria-hidden /> Tidy</button>
            </div>
            <div className="min-w-0 truncate text-[11px] text-text-secondary" data-testid="brf-flow-summary">
              <span className="mr-2 text-text-muted">{graph.nodes.length} nodes · {c.output} lines · {c.check} checks</span>
              {ev ? <Rich text={ev.summary} className="inline text-[11px] text-text-secondary" /> : null}
            </div>
          </div>
        ) : null}
        <div className="flex min-h-0 flex-1">
          <div className="relative min-w-0 flex-1">
            {hasGraph ? (
              <ReactFlow nodes={rfNodes} edges={rfEdges} nodeTypes={NODE_TYPES} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
                         deleteKeyCode={["Backspace", "Delete"]} minZoom={0.2} maxZoom={1.6} proOptions={{ hideAttribution: true }} fitView fitViewOptions={{ padding: 0.04, minZoom: 0.8, maxZoom: 1.1 }}>
                <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
                <Controls showInteractive={false} position="bottom-left" />
              </ReactFlow>
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-[13px] text-text-secondary" data-testid="brf-empty">
                <FileSpreadsheet size={28} className="text-text-muted" aria-hidden />
                <div>Attach a BRF template in the chat, or pick a quick start.</div>
                <div className="text-[12px] text-text-muted">The flow of sources, calculations, checks and output lines appears here.</div>
              </div>
            )}
          </div>
          {sel ? <Inspector key={sel.id} n={sel} v={ev?.values[sel.id]} graph={graph} onChange={(patch) => edit(updateNode(graph, sel.id, patch))}
                            onDelete={() => { setSelected([]); edit(removeNodes(graph, [sel.id])); }} onClose={() => setSelected([])} /> : null}
        </div>
      </section>

      {/* ------------------------------------------------------------ populated return (after Run) */}
      {run ? <Result run={run} title={title} onExport={() => void doExport()} /> : null}
    </div>
  );
}

// ------------------------------------------------------------------ node card
type BrfNodeData = { n: BrfNode; v?: NodeValue };

function BrfNodeCard({ data, selected }: NodeProps) {
  const { n, v } = data as BrfNodeData;
  const tone = v?.error ? "text-rose-700 dark:text-rose-300" : v?.status === "FAIL" ? "text-rose-700 dark:text-rose-300" : v?.status === "PASS" ? "text-emerald-700 dark:text-emerald-300" : "text-text-primary";
  return (
    <div className={cn("rounded-md border border-border border-l-4 bg-surface px-2.5 py-1.5 text-left shadow-sm", KIND[n.kind].cls, selected && "ring-2 ring-accent")}
         style={{ width: NODE_W }} title={v?.error ?? v?.detail ?? describe(n)} data-testid={`brf-node-${n.kind}`}>
      {n.kind !== "source" ? <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-border !bg-surface" /> : null}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 truncate text-[12px] font-medium text-text-primary">{n.label}</div>
        {v && n.kind !== "source" && n.kind !== "transform" ? <div className={cn("shrink-0 text-[12px] font-bold", tone)} data-testid="brf-node-value">{v.error ? "Error" : v.display}</div> : null}
      </div>
      <div className="truncate text-[10.5px] text-text-muted">{v?.error ?? (n.kind === "source" || n.kind === "transform" ? `${describe(n)}${v?.display ? ` · ${v.display}` : ""}` : describe(n))}</div>
      {n.kind !== "output" ? <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-border !bg-surface" /> : null}
    </div>
  );
}
const NODE_TYPES = { brf: BrfNodeCard };

// ------------------------------------------------------------------ inspector
function Inspector({ n, v, graph, onChange, onDelete, onClose }: {
  n: BrfNode; v?: NodeValue; graph: BrfGraph;
  onChange: (p: { label?: string; spec?: Partial<BrfNode["spec"]> }) => void; onDelete: () => void; onClose: () => void;
}) {
  const [label, setLabel] = React.useState(n.label);
  const [spec, setSpec] = React.useState(n.spec);
  const set = (k: keyof BrfNode["spec"], val: unknown) => setSpec((s) => ({ ...s, [k]: val }));
  const inputs = graph.edges.filter((e) => e.target === n.id).map((e) => graph.nodes.find((x) => x.id === e.source)?.label ?? e.source);
  const F = "w-full rounded border border-border bg-surface px-2 py-1 text-[12px] text-text-primary";
  return (
    <aside className="flex w-72 shrink-0 flex-col gap-2 overflow-y-auto border-l border-border bg-surface p-3 text-[12px]" data-testid="brf-inspector">
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-muted"><span className={cn("h-2 w-2 rounded-full", KIND[n.kind].dot)} />{KIND[n.kind].add}</span>
        <button type="button" onClick={onClose} aria-label="Close" className="rounded p-0.5 hover:bg-surface-hover"><X size={14} /></button>
      </div>
      {v ? (
        <div className={cn("rounded-md bg-surface-hover px-2 py-1.5", v.error && "text-rose-700 dark:text-rose-300")} data-testid="brf-inspector-value">
          <strong className="text-[14px]">{v.error ? "Error" : v.display}</strong>
          {v.error || v.detail ? <div className="text-[11px]">{v.error ?? v.detail}</div> : null}
        </div>
      ) : null}
      <label className="space-y-0.5"><span className="text-text-secondary">Label</span><input value={label} onChange={(e) => setLabel(e.target.value)} className={F} data-testid="brf-insp-label" /></label>
      {n.kind === "source" ? (
        <label className="space-y-0.5"><span className="text-text-secondary">Dataset</span>
          <select value={spec.dataset ?? ""} onChange={(e) => set("dataset", e.target.value)} className={F} data-testid="brf-insp-dataset">
            {DATASET_OPTIONS.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
          </select></label>
      ) : null}
      {n.kind === "transform" ? <>
        <label className="space-y-0.5"><span className="text-text-secondary">Step</span>
          <select value={spec.op ?? "filter"} onChange={(e) => set("op", e.target.value)} className={F} data-testid="brf-insp-op">
            <option value="period">Filter to period</option><option value="filter">Filter</option><option value="join">Join (on borrower_id)</option>
          </select></label>
        {spec.op === "filter" ? <label className="space-y-0.5"><span className="text-text-secondary">Where</span><input value={spec.where ?? ""} onChange={(e) => set("where", e.target.value)} className={F} placeholder="stage == 3 and sector == 'Construction'" data-testid="brf-insp-where" /></label> : null}
      </> : null}
      {n.kind === "calc" ? <>
        <label className="space-y-0.5"><span className="text-text-secondary">Calculation</span>
          <select value={spec.op ?? "sum"} onChange={(e) => set("op", e.target.value)} className={F} data-testid="brf-insp-op">
            <option value="sum">Σ sum of a field</option><option value="count">Count rows</option><option value="mean">Mean of a field</option><option value="max">Max of a field</option>
            <option value="pct">A ÷ B as %</option><option value="ratio">A ÷ B</option><option value="diff">A − B</option><option value="add">A + B</option><option value="const">Constant</option>
          </select></label>
        {["sum", "mean", "max"].includes(spec.op ?? "sum") ? <label className="space-y-0.5"><span className="text-text-secondary">Field</span><input value={spec.field ?? ""} onChange={(e) => set("field", e.target.value)} className={F} placeholder="ead_sar_mn" data-testid="brf-insp-field" /></label> : null}
        {["sum", "count", "mean", "max"].includes(spec.op ?? "sum") ? <label className="space-y-0.5"><span className="text-text-secondary">Where (optional)</span><input value={spec.where ?? ""} onChange={(e) => set("where", e.target.value)} className={F} placeholder="sector == 'Construction'" data-testid="brf-insp-where" /></label> : null}
        {spec.op === "const" ? <label className="space-y-0.5"><span className="text-text-secondary">Value</span><input type="number" value={spec.value ?? 0} onChange={(e) => set("value", Number(e.target.value))} className={F} /></label> : null}
        <label className="space-y-0.5"><span className="text-text-secondary">Shown as</span>
          <select value={spec.unit ?? "sar"} onChange={(e) => set("unit", e.target.value)} className={F}>
            <option value="sar">SAR</option><option value="pct">%</option><option value="count">Count</option><option value="ratio">Ratio</option>
          </select></label>
      </> : null}
      {n.kind === "check" ? <>
        <label className="space-y-0.5"><span className="text-text-secondary">Rule</span>
          <select value={spec.op ?? "eq"} onChange={(e) => set("op", e.target.value)} className={F} data-testid="brf-insp-op">
            <option value="eq">A equals B</option><option value="le">A at most B</option><option value="ge">A at least B</option><option value="zero">A is zero</option>
          </select></label>
        <label className="space-y-0.5"><span className="text-text-secondary">Description</span><input value={spec.rule ?? ""} onChange={(e) => set("rule", e.target.value)} className={F} /></label>
      </> : null}
      {n.kind === "output" ? <label className="space-y-0.5"><span className="text-text-secondary">Template line code</span><input value={spec.cell ?? ""} onChange={(e) => set("cell", e.target.value)} className={F} /></label> : null}
      {n.kind !== "source" ? (
        <div className="text-[11px] text-text-muted" data-testid="brf-insp-inputs">
          Inputs{["pct", "ratio", "diff"].includes(spec.op ?? "") || n.kind === "check" ? " (A, B in order)" : ""}: {inputs.length ? inputs.join(" · ") : "none. Drag from a node's right handle to this node."}
        </div>
      ) : null}
      <div className="mt-auto flex gap-2 pt-2">
        <button type="button" className={PRIMARY} onClick={() => onChange({ label, spec })} data-testid="brf-insp-apply">Apply</button>
        <button type="button" className={BTN} onClick={onDelete} data-testid="brf-insp-delete"><Trash2 size={13} aria-hidden /> Delete</button>
      </div>
    </aside>
  );
}

// ------------------------------------------------------------------ populated return
function Result({ run, title, onExport }: { run: Evaluation; title: string; onExport: () => void }) {
  return (
    <section className="space-y-3 rounded-xl border border-border bg-surface p-4" data-testid="brf-result">
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 className="text-[14px] font-semibold">{title} · {run.period}</h2>
        <InfoPopover title="About this return"><p>Each template line with its value at the locked period, computed on the books through the flow above; totals equal the Cockpit&apos;s. The checks run on the same figures.</p></InfoPopover>
        <Rich text={run.summary} className="text-[12px] text-text-secondary" />
        <button type="button" className={cn(BTN, "ml-auto")} onClick={onExport} data-testid="brf-export"><FileDown size={14} aria-hidden /> Excel</button>
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-[12px]" data-testid="brf-grid">
            <thead className="bg-surface-hover text-left text-text-secondary"><tr><th className="px-2 py-1.5">Code</th><th className="px-2 py-1.5">Line</th><th className="px-2 py-1.5 text-right">Value</th></tr></thead>
            <tbody>{run.outputs.map((o) => (
              <tr key={o.id} className="border-t border-border">
                <td className="px-2 py-1 font-mono text-text-muted">{o.code}</td><td className="px-2 py-1">{o.label}</td>
                <td className={cn("px-2 py-1 text-right font-semibold", o.value == null && "text-rose-700 dark:text-rose-300")}>{o.error ? "Error" : o.display}</td>
              </tr>))}</tbody>
          </table>
        </div>
        <div className="space-y-1.5" data-testid="brf-checks">
          {run.checks.map((c) => (
            <div key={c.id} className="rounded-md border border-border p-2 text-[12px]">
              <div className="flex items-center justify-between gap-2"><span className="font-medium">{c.label}</span><Pill tone={STATUS_TONE[c.status ?? ""] ?? "bad"}>{c.status ?? "Error"}</Pill></div>
              <div className="text-text-secondary">{c.error ?? c.detail ?? c.rule}</div>
            </div>
          ))}
        </div>
      </div>
      <PoweredTrace powered={run.powered_by} trace={run.trace} testId="brf-run" />
    </section>
  );
}
