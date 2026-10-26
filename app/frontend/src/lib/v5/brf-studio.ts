/**
 * BRF studio as chat + flowchart (PLAN_R10 Session B, item 13): client and pure graph helpers.
 *
 * The return is a graph: source (domain dataset) → transform (period, filter, join) → calc → check → output.
 * The chat (`/api/v1/brf/studio/chat`) builds and edits it; the canvas edits it directly; every change is sent to
 * `/evaluate` and the outputs recompute. No React here so `npm test` can import it.
 */
import { friendlyError } from "./errors.ts";

export type BrfKind = "source" | "transform" | "calc" | "check" | "output";
export interface BrfSpec {
  dataset?: string; op?: string; where?: string; field?: string; unit?: string; inputs?: string[];
  cell?: string; rule?: string; tol?: number; value?: number; on?: string; fields?: string[]; note?: string;
}
export interface BrfNode { id: string; kind: BrfKind; label: string; spec: BrfSpec; position?: { x: number; y: number } }
export interface BrfEdge { id: string; source: string; target: string }
export interface BrfGraph { nodes: BrfNode[]; edges: BrfEdge[] }
export interface NodeValue { value?: number | null; unit?: string; display: string; status?: string; detail?: string; error?: string; rows?: number }
export interface BrfOutput extends NodeValue { id: string; code: string; label: string }
export interface BrfCheckResult extends NodeValue { id: string; label: string; rule: string }
export interface Evaluation {
  period: string; values: Record<string, NodeValue>; outputs: BrfOutput[]; checks: BrfCheckResult[]; summary: string;
  powered_by: { pack: string; pack_id: string; rule: string; article: string; confidence: string };
  trace: { sources: string[]; steps: string[]; rule: string; article: string; row_count: number; period: string; engine: string };
}
export interface ChatReply {
  reply: string; graph: BrfGraph; template: string[]; action: "none" | "build" | "edit" | "lock" | "run" | "publish";
  period: string; file: string | null; evaluation: Evaluation | null;
}
export interface QuickInfo { quick: { id: string; title: string; lines: number }[]; templates: string[]; periods: string[]; as_of: string; help: string }

export function studioOrigin(): string {
  return (process.env.NEXT_PUBLIC_QUERIES_API ?? "http://127.0.0.1:8516").replace(/\/$/, "");
}
export const studioUrl = (path: string) => `${studioOrigin()}/api/v1/brf/studio${path}`;

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, credentials: "include", cache: "no-store" });
  } catch {
    throw new Error("The BRF studio is temporarily unavailable. Please try again in a moment.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(friendlyError("BRF", response.status, body));
  return body as T;
}

/** Positions are UI state; the server never needs them. */
export function stripPositions(g: BrfGraph): BrfGraph {
  return { nodes: g.nodes.map((n) => ({ id: n.id, kind: n.kind, label: n.label, spec: n.spec })), edges: g.edges };
}

export const studio = {
  quick: () => request<QuickInfo>(studioUrl("/quick")),
  templateUrl: (name: string) => studioUrl(`/templates/${encodeURIComponent(name)}`),
  chat: (message: string, graph: BrfGraph, template: string[], period: string, file?: File | null) => {
    const f = new FormData();
    f.append("message", message);
    f.append("graph", JSON.stringify(stripPositions(graph)));
    f.append("template", JSON.stringify(template));
    f.append("period", period);
    if (file) f.append("file", file);
    return request<ChatReply>(studioUrl("/chat"), { method: "POST", body: f });
  },
  evaluate: (graph: BrfGraph, period: string) =>
    request<Evaluation>(studioUrl("/evaluate"), { method: "POST", body: JSON.stringify({ graph: stripPositions(graph), period }), headers: { "Content-Type": "application/json" } }),
  /** The populated return as a workbook (POST, so the flow travels in the body). */
  exportXlsx: async (title: string, graph: BrfGraph, period: string): Promise<Blob> => {
    let r: Response;
    try {
      r = await fetch(studioUrl("/export.xlsx"), {
        method: "POST", credentials: "include", body: JSON.stringify({ title, graph: stripPositions(graph), period }), headers: { "Content-Type": "application/json" },
      });
    } catch {
      throw new Error("The BRF studio is temporarily unavailable. Please try again in a moment.");
    }
    if (!r.ok) throw new Error(friendlyError("BRF", r.status, await r.json().catch(() => null)));
    return r.blob();
  },
  publish: (title: string, graph: BrfGraph, period: string) =>
    request<{ id: string; lines: number; checks_pass: number; checks: number; summary: string; at: string }>(studioUrl("/publish"), {
      method: "POST", body: JSON.stringify({ title, graph: stripPositions(graph), period }), headers: { "Content-Type": "application/json" },
    }),
};

// ------------------------------------------------------------------ layout
export const NODE_W = 210;
export const NODE_H = 58;
const COL_GAP = 70;
const ROW_GAP = 14;

/**
 * Column of a node: sources 0, period 1, filters and joins 2 (3 when fed by another filter or join),
 * aggregate calcs 4, derived calcs 5 (6 when fed by a derived calc), checks 7, outputs 8.
 */
export function columnOf(n: BrfNode, g: BrfGraph): number {
  const parents = () => g.edges.filter((e) => e.target === n.id).map((e) => g.nodes.find((x) => x.id === e.source));
  const derived = (x?: BrfNode) => !!x && x.kind === "calc" && ["ratio", "pct", "diff", "add"].includes(x.spec.op ?? "");
  if (n.kind === "source") return 0;
  if (n.kind === "transform") {
    if (n.spec.op === "period") return 1;
    return parents().some((p) => p && p.kind === "transform" && p.spec.op !== "period") ? 3 : 2;
  }
  if (n.kind === "calc") {
    if (!derived(n)) return 4;
    return parents().some((p) => derived(p)) ? 6 : 5;
  }
  return n.kind === "check" ? 7 : 8;
}

/**
 * Left-to-right layout; nodes that already have a position (dragged or added by the user) keep it.
 * Within a column, nodes are ordered by the mean row of their inputs (one barycentre pass) so edges cross less.
 */
export function layout(g: BrfGraph): BrfGraph {
  const colOf = new Map(g.nodes.map((n) => [n.id, columnOf(n, g)]));
  const cols = Array.from(new Set(colOf.values())).sort((a, b) => a - b);
  const parents = new Map<string, string[]>(g.nodes.map((n) => [n.id, []]));
  for (const e of g.edges) parents.get(e.target)?.push(e.source);
  const row = new Map<string, number>();
  for (const c of cols) {
    const inCol = g.nodes.filter((n) => colOf.get(n.id) === c);
    const key = (n: BrfNode, i: number) => {
      const ps = (parents.get(n.id) ?? []).map((p) => row.get(p)).filter((r): r is number => r !== undefined);
      return ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : i;
    };
    inCol.map((n, i) => ({ n, k: key(n, i), i })).sort((a, b) => a.k - b.k || a.i - b.i).forEach((x, r) => row.set(x.n.id, r));
  }
  const xOf = (c: number) => cols.indexOf(c) * (NODE_W + COL_GAP);
  return {
    edges: g.edges,
    nodes: g.nodes.map((n) => (n.position ? n : { ...n, position: { x: xOf(colOf.get(n.id)!), y: (row.get(n.id) ?? 0) * (NODE_H + ROW_GAP) } })),
  };
}

/** Keep the positions of nodes that survive a server round trip (the server drops them). */
export function keepPositions(next: BrfGraph, prev: BrfGraph): BrfGraph {
  const pos = new Map(prev.nodes.filter((n) => n.position).map((n) => [n.id, n.position!]));
  return layout({ edges: next.edges, nodes: next.nodes.map((n) => (pos.has(n.id) ? { ...n, position: pos.get(n.id) } : n)) });
}

// ------------------------------------------------------------------ edits
let seq = 0;
export function newId(kind: BrfKind): string {
  seq += 1;
  return `${kind === "calc" ? "calc" : kind === "check" ? "chk" : kind === "output" ? "out" : kind === "source" ? "src" : "tx"}:u${Date.now().toString(36)}${seq}`;
}

export const DATASET_OPTIONS = [
  { id: "books.corp_facility_quarter", label: "corp_facility_quarter (books)" },
  { id: "books.corp_borrower_quarter", label: "corp_borrower_quarter (books)" },
  { id: "collateral.corp_collateral_quarter", label: "corp_collateral_quarter (collateral)" },
];

export function defaultNode(kind: BrfKind, g: BrfGraph, at?: { x: number; y: number }): BrfNode {
  const id = newId(kind);
  const nextCode = () => {
    const nums = g.nodes.filter((n) => n.kind === "output").map((n) => Number(/^L(\d+)/.exec(n.spec.cell ?? "")?.[1] ?? 0));
    return `L${String((nums.length ? Math.max(...nums) : 0) + 1).padStart(2, "0")}`;
  };
  const base = { id, kind, position: at };
  switch (kind) {
    case "source": return { ...base, label: "corp_collateral_quarter", spec: { dataset: "collateral.corp_collateral_quarter" } };
    case "transform": return { ...base, label: "Filter", spec: { op: "filter", where: "stage == 2" } };
    case "calc": return { ...base, label: "Σ exposure", spec: { op: "sum", field: "ead_sar_mn", unit: "sar" } };
    case "check": return { ...base, label: "Values agree", spec: { op: "eq", tol: 0.01, rule: "first input = second input" } };
    default: { const c = nextCode(); return { ...base, label: `New line ${c}`, spec: { cell: c } }; }
  }
}

export function addNode(g: BrfGraph, n: BrfNode): BrfGraph {
  return { nodes: [...g.nodes, n], edges: g.edges };
}

export function removeNodes(g: BrfGraph, ids: string[]): BrfGraph {
  const s = new Set(ids);
  return { nodes: g.nodes.filter((n) => !s.has(n.id)), edges: g.edges.filter((e) => !s.has(e.source) && !s.has(e.target)) };
}

export function removeEdges(g: BrfGraph, ids: string[]): BrfGraph {
  const s = new Set(ids);
  return { nodes: g.nodes, edges: g.edges.filter((e) => !s.has(e.id)) };
}

/** Connect a → b; an output reads one value, so a new link into an output replaces the old one. No self-loops or duplicates. */
export function connect(g: BrfGraph, source: string, target: string): BrfGraph {
  if (source === target || g.edges.some((e) => e.source === source && e.target === target)) return g;
  const t = g.nodes.find((n) => n.id === target);
  const edges = t?.kind === "output" ? g.edges.filter((e) => e.target !== target) : g.edges;
  const nodes = g.nodes.map((n) => (n.id === target && n.spec.inputs ? { ...n, spec: { ...n.spec, inputs: [...n.spec.inputs.filter((i) => i !== source), source] } } : n));
  return { nodes, edges: [...edges, { id: `e:${source}>${target}`, source, target }] };
}

export function updateNode(g: BrfGraph, id: string, patch: { label?: string; spec?: Partial<BrfSpec> }): BrfGraph {
  return { edges: g.edges, nodes: g.nodes.map((n) => (n.id === id ? { ...n, label: patch.label ?? n.label, spec: { ...n.spec, ...(patch.spec ?? {}) } } : n)) };
}

export function counts(g: BrfGraph): Record<BrfKind, number> {
  const c: Record<BrfKind, number> = { source: 0, transform: 0, calc: 0, check: 0, output: 0 };
  for (const n of g.nodes) c[n.kind] += 1;
  return c;
}

/** One-line description of what a node does, for the node card. */
export function describe(n: BrfNode): string {
  const s = n.spec;
  if (n.kind === "source") return s.dataset ?? "";
  if (n.kind === "transform") return s.op === "period" ? "reporting_quarter = locked period" : s.op === "join" ? `join on ${s.on ?? "borrower_id"}` : s.where ?? "";
  if (n.kind === "calc") {
    if (s.op === "const") return `constant ${s.value ?? ""}`;
    if (s.op === "count") return `count${s.where ? ` where ${s.where}` : ""}`;
    if (s.op === "pct") return "A ÷ B × 100";
    if (s.op === "ratio") return "A ÷ B";
    if (s.op === "diff") return "A − B";
    if (s.op === "add") return "A + B";
    return `${s.op === "mean" ? "mean" : s.op === "max" ? "max" : "Σ"} ${s.field ?? ""}${s.where ? ` where ${s.where}` : ""}`;
  }
  if (n.kind === "check") return s.rule ?? s.op ?? "";
  return s.cell ? `Line ${s.cell}` : "";
}
