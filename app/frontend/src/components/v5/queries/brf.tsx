"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { FileDown, Lock, Play, Send, Upload } from "lucide-react";

import { InfoPopover } from "@/components/ui/info-popover";
import { DataTable, Pill, PoweredTrace, Rich, STATUS_TONE } from "@/components/v5/queries/parts";
import { ErrorBox, Loading, PageTop } from "@/components/v5/workspace/parts";
import { brf, type BrfReturn, type BrfReturnCard, type BrfRun, type FlowNode } from "@/lib/v5/queries";
import { cn } from "@/lib/utils";

const BTN = "inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-[12px] text-text-secondary hover:bg-surface-hover disabled:opacity-50";
const PRIMARY = "inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-3 text-[12px] font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50";

/** Process-flow colours: sources blue → transformations purple → calculations amber → checks red → outputs green. */
export const KIND_STYLE: Record<FlowNode["kind"], { label: string; cls: string }> = {
  source: { label: "Sources", cls: "border-sky-500 bg-sky-50 text-sky-900 dark:bg-sky-950/50 dark:text-sky-100" },
  transform: { label: "Transformations", cls: "border-violet-500 bg-violet-50 text-violet-900 dark:bg-violet-950/50 dark:text-violet-100" },
  calc: { label: "Calculations", cls: "border-amber-500 bg-amber-50 text-amber-900 dark:bg-amber-950/50 dark:text-amber-100" },
  check: { label: "Checks", cls: "border-rose-500 bg-rose-50 text-rose-900 dark:bg-rose-950/50 dark:text-rose-100" },
  output: { label: "Outputs", cls: "border-emerald-500 bg-emerald-50 text-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-100" },
};
const KINDS: FlowNode["kind"][] = ["source", "transform", "calc", "check", "output"];

export function BrfStudio() {
  const params = useSearchParams();
  const router = useRouter();
  const rid = params.get("r");
  return rid ? <ReturnView rid={rid} /> : <Returns open={(r) => router.push(`/brf?r=${r}`)} />;
}

function Returns({ open }: { open: (rid: string) => void }) {
  const [list, setList] = React.useState<BrfReturnCard[] | null>(null);
  const [error, setError] = React.useState("");
  React.useEffect(() => { brf.list().then(setList).catch((e) => setError(e instanceof Error ? e.message : String(e))); }, []);
  return (
    <div className="space-y-6" data-testid="brf-home">
      <PageTop eyebrow="Functionalities" title="BRF studio" back={{ href: "/workspace", label: "Workspace" }}
        about={<p>Credit returns built on the bank&apos;s domains: upload the template, see each field mapped to domain, dataset, fields, filters and calculations, edit the mapping, review the process flow and the proposed checks, then Lock the period, Run and Publish. Powered by P7.</p>} />
      {error ? <ErrorBox error={error} /> : null}
      {list === null ? <Loading what="Loading returns…" /> : (
        <div className="grid gap-4 md:grid-cols-2">
          {list.map((r) => (
            <button key={r.id} type="button" onClick={() => open(r.id)} className="rounded-xl border border-border bg-surface p-4 text-left hover:border-accent" data-testid={`brf-card-${r.id}`}>
              <div className="flex items-center justify-between"><span className="text-[12px] font-semibold text-text-muted">{r.id} · {r.frequency}</span><Pill tone={STATUS_TONE[r.state]}>{r.state}</Pill></div>
              <div className="mt-2 text-[16px] font-semibold text-text-primary">{r.title}</div>
              <div className="mt-1 text-[12px] text-text-secondary">{r.fields} fields mapped · {r.article}{r.period ? ` · period ${r.period}` : ""}</div>
              {r.schedule ? <div className="mt-1 text-[12px] text-text-muted">Schedule: {r.schedule}</div> : null}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ReturnView({ rid }: { rid: string }) {
  const [r, setR] = React.useState<BrfReturn | null>(null);
  const [run, setRun] = React.useState<BrfRun | null>(null);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState("");
  const [period, setPeriod] = React.useState("");
  const [node, setNode] = React.useState<FlowNode | null>(null);
  const [cmd, setCmd] = React.useState("");
  const [thread, setThread] = React.useState<{ who: "you" | "studio"; text: string }[]>([]);
  const file = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    brf.get(rid).then((x) => { setR(x); setPeriod(x.period ?? x.as_of); setThread([{ who: "studio", text: mapSummary(x) }]); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [rid]);

  const act = async <T,>(label: string, fn: () => Promise<T>, after: (x: T) => void) => {
    setBusy(label); setError("");
    try { after(await fn()); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); }
  };

  const say = (text: string) => {
    if (!r || !text.trim()) return;
    const m = text.match(/^\s*(?:set\s+)?([A-Z0-9_]+)\s+(filter|filters|calc|calculation|label)\s+(?:to\s+)?(.+)$/i);
    setThread((t) => [...t, { who: "you", text }]);
    setCmd("");
    if (!m || !r.fields.some((f) => f.id === m[1].toUpperCase())) {
      setThread((t) => [...t, { who: "studio", text: `Name a field and what to change, for example “${r.fields[0]?.id} filter stage = 2”. Fields: ${r.fields.map((f) => f.id).join(", ")}.` }]);
      return;
    }
    const key = m[2].toLowerCase().startsWith("filter") ? "filters" : m[2].toLowerCase().startsWith("calc") ? "calc" : "label";
    void act("field", () => brf.field(rid, { id: m[1].toUpperCase(), [key]: m[3] }), (x) => {
      setR(x); setRun(null);
      setThread((t) => [...t, { who: "studio", text: `Updated ${m[1].toUpperCase()}: ${key} is now “${m[3]}”. The return is back in Draft; Lock and Run again.` }]);
    });
  };

  if (error && !r) return <ErrorBox error={error} />;
  if (!r) return <Loading what="Opening the return…" />;
  return (
    <div className="space-y-5" data-testid="brf-return">
      <PageTop eyebrow={`BRF studio · ${r.id}`} title={r.title} back={{ href: "/brf", label: "BRF studio" }}
        subtitle={<>State <strong>{r.state}</strong>{r.period ? <> · period <strong>{r.period}</strong></> : null}{r.template ? <> · template {r.template.file}</> : null}</>}
        actions={<>
          <input ref={file} type="file" accept=".xlsx,.xls,.csv,.pdf,.docx" className="hidden" data-testid="brf-file"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) void act("upload", () => brf.upload(rid, f), (x) => { setR(x); setThread((t) => [...t, { who: "studio", text: `Read ${f.name}. ${mapSummary(x)}` }]); }); e.target.value = ""; }} />
          <button type="button" className={BTN} onClick={() => file.current?.click()} disabled={!!busy} data-testid="brf-upload"><Upload size={14} aria-hidden /> Upload template</button>
          <select value={period} onChange={(e) => setPeriod(e.target.value)} className="h-8 rounded-md border border-border bg-surface px-2 text-[12px]" data-testid="brf-period">
            {r.periods.map((p) => <option key={p}>{p}</option>)}
          </select>
          <button type="button" className={BTN} disabled={!!busy} onClick={() => void act("lock", () => brf.lock(rid, period), (x) => { setR(x); setRun(null); })} data-testid="brf-lock"><Lock size={14} aria-hidden /> Lock</button>
          <button type="button" className={PRIMARY} disabled={!!busy || !r.period || r.state === "Draft"} onClick={() => void act("run", () => brf.run(rid), (x) => { setRun(x); void brf.get(rid).then(setR); })} data-testid="brf-run"><Play size={14} aria-hidden /> {busy === "run" ? "Running…" : "Run"}</button>
          <button type="button" className={BTN} disabled={!!busy || r.state !== "Run"} onClick={() => void act("publish", () => brf.publish(rid, "Quarterly, 15 working days after quarter-end"), setR)} data-testid="brf-publish"><Send size={14} aria-hidden /> Publish</button>
          <a className={BTN} href={brf.exportUrl(rid)} data-testid="brf-export"><FileDown size={14} aria-hidden /> Excel</a>
        </>} />
      {error ? <ErrorBox error={error} /> : null}

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <section className="space-y-2 rounded-xl border border-border bg-surface p-4">
          <div className="flex items-center gap-2"><h2 className="text-[14px] font-semibold">Process flow</h2>
            <InfoPopover title="Process flow"><p>Sources (blue) feed transformations (purple), then calculations (amber) and checks (red) before the output grid (green). Click a node to see or edit it.</p></InfoPopover></div>
          <Flow nodes={r.flow.nodes} selected={node?.id ?? ""} onPick={setNode} />
          {node ? <NodeEditor key={`${node.id}|${node.detail}`} node={node} r={r} busy={!!busy} onSave={(body) => void act("field", () => brf.field(rid, body), (x) => { setR(x); setRun(null); setNode(x.flow.nodes.find((n) => n.id === node.id) ?? null); })} /> : null}
        </section>
        <section className="flex flex-col rounded-xl border border-border bg-surface p-4" data-testid="brf-thread">
          <h2 className="mb-2 text-[14px] font-semibold">Mapping thread</h2>
          <div className="flex-1 space-y-2 overflow-y-auto text-[13px]" style={{ maxHeight: 340 }}>
            {thread.map((m, i) => (
              <div key={i} className={cn("rounded-lg px-3 py-2", m.who === "you" ? "ml-6 bg-accent/10" : "mr-6 bg-surface-hover")}>{m.text}</div>
            ))}
          </div>
          <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); say(cmd); }}>
            <input value={cmd} onChange={(e) => setCmd(e.target.value)} placeholder={`e.g. ${r.fields[0]?.id ?? ""} filter stage = 2`} className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1 text-[13px]" data-testid="brf-say" />
            <button type="submit" className={PRIMARY} data-testid="brf-say-send">Send</button>
          </form>
        </section>
      </div>

      <section className="space-y-2">
        <h2 className="text-[14px] font-semibold">Field map</h2>
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-[12px]" data-testid="brf-fields">
            <thead className="bg-surface-hover text-left text-text-secondary"><tr><th className="px-2 py-1.5">Field</th><th className="px-2 py-1.5">Label</th><th className="px-2 py-1.5">Domain</th><th className="px-2 py-1.5">Dataset</th><th className="px-2 py-1.5">Fields</th><th className="px-2 py-1.5">Filters</th><th className="px-2 py-1.5">Calculation</th></tr></thead>
            <tbody>{r.fields.map((f) => (
              <tr key={f.id} className="cursor-pointer border-t border-border hover:bg-surface-hover" onClick={() => setNode(r.flow.nodes.find((n) => n.id === `calc:${f.id}`) ?? null)}>
                <td className="px-2 py-1 font-mono">{f.id}{f.edited ? " ✎" : ""}</td><td className="px-2 py-1">{f.label}</td><td className="px-2 py-1">{f.domain}</td><td className="px-2 py-1">{f.dataset}</td>
                <td className="px-2 py-1">{f.fields.join(", ")}</td><td className="px-2 py-1">{f.filters}</td><td className="px-2 py-1">{f.calc}</td>
              </tr>))}</tbody>
          </table>
        </div>
      </section>

      <section className="space-y-2" data-testid="brf-checks">
        <h2 className="text-[14px] font-semibold">Checks</h2>
        <div className="grid gap-2 md:grid-cols-3">
          {(run?.checks ?? r.checks).map((c) => (
            <div key={c.id} className="rounded-lg border border-border p-3 text-[12px]">
              <div className="flex items-center justify-between gap-2"><span className="font-medium text-text-primary">{c.label}</span>{c.status ? <Pill tone={STATUS_TONE[c.status]}>{c.status}</Pill> : <Pill>Proposed</Pill>}</div>
              <div className="mt-1 text-text-secondary">{c.detail ?? c.rule}</div>
            </div>
          ))}
        </div>
      </section>

      {run ? (
        <section className="space-y-3 rounded-xl border border-border bg-surface p-4" data-testid="brf-result">
          <div className="flex items-center gap-2"><h2 className="text-[14px] font-semibold">{run.title} · {run.period}</h2>
            <InfoPopover title="About this return"><p>The populated grid at the locked period, computed on the books; totals equal the Cockpit&apos;s.</p></InfoPopover></div>
          <Rich text={run.note} />
          <DataTable table={run.grid} testId="brf-grid" max={40} />
          <PoweredTrace powered={run.powered_by} trace={run.trace} testId="brf-run" />
        </section>
      ) : null}
    </div>
  );
}

function mapSummary(r: BrfReturn): string {
  const ds = Array.from(new Set(r.fields.map((f) => f.dataset).filter((d) => d !== "derived")));
  return `${r.fields.length} fields of “${r.title}” map to existing domains (${ds.join(", ")}). ${r.checks.length} checks proposed. Change a mapping here or click a node in the flow.`;
}

function Flow({ nodes, selected, onPick }: { nodes: FlowNode[]; selected: string; onPick: (n: FlowNode) => void }) {
  return (
    <div className="grid gap-3 overflow-x-auto md:grid-cols-5" data-testid="brf-flow">
      {KINDS.map((k) => (
        <div key={k} className="space-y-2">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">{KIND_STYLE[k].label}</div>
          {nodes.filter((n) => n.kind === k).map((n) => (
            <button key={n.id} type="button" onClick={() => onPick(n)} title={n.detail} data-testid={`brf-node-${n.id}`}
                    className={cn("block w-full rounded-md border-l-4 px-2 py-1.5 text-left text-[12px] shadow-sm", KIND_STYLE[k].cls, selected === n.id && "ring-2 ring-accent")}>
              {n.label}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}

function NodeEditor({ node, r, busy, onSave }: { node: FlowNode; r: BrfReturn; busy: boolean; onSave: (body: { id: string; filters?: string; calc?: string; label?: string }) => void }) {
  const field = node.kind === "calc" ? r.fields.find((f) => `calc:${f.id}` === node.id) : undefined;
  const [filters, setFilters] = React.useState(field?.filters ?? "");
  const [calc, setCalc] = React.useState(field?.calc ?? "");
  return (
    <div className={cn("rounded-md border-l-4 p-3 text-[12px]", KIND_STYLE[node.kind].cls)} data-testid="brf-node-editor">
      <div className="font-semibold">{node.label}</div>
      <div className="mt-1">{node.detail}</div>
      {field ? (
        <div className="mt-2 grid gap-2 md:grid-cols-[1fr_1fr_auto]">
          <label className="space-y-0.5"><span>Filters</span><input value={filters} onChange={(e) => setFilters(e.target.value)} className="w-full rounded border border-border bg-surface px-2 py-1 text-text-primary" data-testid="brf-node-filters" /></label>
          <label className="space-y-0.5"><span>Calculation</span><input value={calc} onChange={(e) => setCalc(e.target.value)} className="w-full rounded border border-border bg-surface px-2 py-1 text-text-primary" data-testid="brf-node-calc" /></label>
          <button type="button" disabled={busy} className={cn(PRIMARY, "self-end")} onClick={() => onSave({ id: field.id, filters, calc })} data-testid="brf-node-save">Save</button>
        </div>
      ) : <div className="mt-1 text-[11px] opacity-80" title="Sources, transformations, checks and the output follow from the field map; edit a calculation node to change them.">Follows from the field map</div>}
    </div>
  );
}
