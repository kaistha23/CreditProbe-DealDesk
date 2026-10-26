/**
 * The relationship graph as a Plotly figure (Borrower 360, Relationships tab).
 *
 * Pure: it carries exactly the API's nodes, edges and positions (backend/b360/graph.py computes the layout).
 *   node colour = Early Warning band      node size = exposure (area ~ SAR)      focal node = ringed
 *   edge style  = relationship type        edge arrow = direction (supplier to buyer, guarantor to guaranteed, parent to member)
 * Filtering by type is done here: a type switched off removes its edges, and any node left with no visible link
 * (other than the borrower in the middle) goes with them.
 */

export type Kind = "group" | "supplier" | "customer" | "guarantor" | "collateral" | "person" | "household" | "employer";

export interface GNode {
  id: string; type: "borrower" | "customer" | "person" | "external"; name: string | null; sector?: string | null; sub_sector?: string | null;
  region?: string | null; rating?: string | null; ews_band: string; ews_score?: number | null; exposure: number; ecl?: number;
  hop: number; is_focal: boolean; x: number; y: number; href?: string; watchlist?: boolean;
  roles?: { borrower_id: string; role: string; ownership_pct: number | null }[]; household_role?: string | null;
  /** PLAN_R9 B7: classification (Stage 3, UTP, SICR, Watch…), its colour band, and an off-book note. */
  classification?: string; class_band?: string; note?: string; level?: string; worst_stage?: number;
}
export interface GEdge {
  id: string; source: string; target: string; type: string; kind: Kind; label: string; directed: boolean;
  ownership_pct?: number | null; purchase_share_pct?: number | null; revenue_share_pct?: number | null;
  annual_value_sar_mn?: number | null; guarantee_amount_sar_mn?: number | null;
}
export interface GraphPayload {
  domain_id: "corporate" | "retail"; customer_id: string; period: string; depth: number; focal: GNode;
  nodes: GNode[]; edges: GEdge[]; legend: Record<string, { label: string; count: number }>;
  truncated: { shown?: number; available?: number; note?: string }; bands: string[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  analytics: any;
  /** PLAN_R9 B7: P5 Network Intelligence. */
  network_intelligence?: NetworkIntelligence; case?: { case: string; proposal: string };
}
export interface NetworkInsight { key: string; title: string; text: string; severity: "high" | "medium" | "low"; ids?: string[] }
export interface NetworkIntelligence {
  insights: NetworkInsight[]; cross_default_required: boolean; classification_counts: Record<string, number>;
  case?: { case: string; proposal: string } | null; levels: Record<string, string>;
  powered_by: { id: string; name: string; articles?: string[]; rules?: string[]; confidence: string; trace: string };
}

export const BAND_COLOURS: Record<string, string> = {
  critical: "#dc2626", high: "#f97316", moderate: "#eab308", low: "#22c55e", none: "#94a3b8",
};
export const BAND_LABEL: Record<string, string> = {
  critical: "Critical", high: "High", moderate: "Moderate", low: "Low", none: "Not warned",
};
export const KIND_STYLE: Record<Kind, { colour: string; dash: "solid" | "dash" | "dot" | "dashdot"; width: number; label: string }> = {
  group: { colour: "#6366f1", dash: "solid", width: 3, label: "Group" },
  supplier: { colour: "#0ea5e9", dash: "solid", width: 2.2, label: "Supplier" },
  customer: { colour: "#10b981", dash: "solid", width: 2.2, label: "Customer" },
  guarantor: { colour: "#f59e0b", dash: "dash", width: 2.2, label: "Guarantor" },
  collateral: { colour: "#a855f7", dash: "dot", width: 2.2, label: "Shared collateral" },
  person: { colour: "#64748b", dash: "dashdot", width: 1.4, label: "Owner or director" },
  household: { colour: "#ec4899", dash: "solid", width: 2.6, label: "Household" },
  employer: { colour: "#14b8a6", dash: "solid", width: 2.6, label: "Employer" },
};
export const KIND_ORDER: Kind[] = ["group", "supplier", "customer", "guarantor", "collateral", "person", "household", "employer"];

export function sar(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `SAR ${v >= 100 ? v.toLocaleString("en-US", { maximumFractionDigits: 0 }) : v.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}m`;
}

/** Edges whose kind is on, and the nodes still connected to the borrower in the middle by them. */
export function visible(g: GraphPayload, on: Set<string>): { nodes: GNode[]; edges: GEdge[] } {
  const edges = g.edges.filter((e) => on.has(e.kind));
  const touched = new Set<string>([g.focal.id]);
  for (const e of edges) { touched.add(e.source); touched.add(e.target); }
  return { nodes: g.nodes.filter((n) => touched.has(n.id)), edges };
}

/** Marker diameter in px from exposure: area follows the amount, with a floor so a small name is still clickable. */
export function nodeSize(exposure: number, max: number, crowded = false): number {
  const [floor, span] = crowded ? [11, 20] : [16, 34];
  if (!(exposure > 0) || !(max > 0)) return floor;
  return Math.round(floor + span * Math.sqrt(exposure / max));
}

function trunc(s: string | null | undefined, n: number): string {
  const t = s ?? "";
  return t.length > n ? `${t.slice(0, n - 1)}…` : t;
}

function hoverNode(n: GNode): string {
  if (n.type === "person") {
    return `<b>${n.name}</b><br>${(n.roles ?? []).map((r) => `${r.role} of ${r.borrower_id}${r.ownership_pct ? ` (${r.ownership_pct.toFixed(1)}%)` : ""}`).join("<br>")}`;
  }
  const lines = [`<b>${n.name ?? n.id}</b> ${n.name ? `(${n.id})` : ""}`, [n.sector, n.sub_sector].filter(Boolean).join(" · ") || n.region || "",
    `Rating ${n.rating ?? "—"} · Early Warning ${BAND_LABEL[n.ews_band] ?? n.ews_band}${n.ews_score !== null && n.ews_score !== undefined ? ` (score ${n.ews_score})` : ""}`,
    `Exposure ${sar(n.exposure)}${n.ecl ? ` · ECL ${sar(n.ecl)}` : ""}`];
  if (n.watchlist) lines.push("On the watchlist");
  if (n.household_role) lines.push(`Household: ${n.household_role}`);
  lines.push(n.is_focal ? "The borrower in the middle" : "Click to open in Borrower 360");
  return lines.filter(Boolean).join("<br>");
}

/** Where along an edge the arrow sits, and the short run before it that points it. */
function along(a: [number, number], b: [number, number], t: number): [number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

export function graphFigure(g: GraphPayload, on: Set<string>): { data: Record<string, unknown>[]; layout: Record<string, unknown>; shown: { nodes: number; edges: number } } {
  const { nodes, edges } = visible(g, on);
  const pos = new Map(nodes.map((n) => [n.id, [n.x, n.y] as [number, number]]));
  const maxExp = Math.max(0, ...nodes.filter((n) => n.type !== "person").map((n) => n.exposure));
  const data: Record<string, unknown>[] = [];

  // one line trace per kind, with an arrow marker part-way along each directed edge
  for (const kind of KIND_ORDER) {
    const es = edges.filter((e) => e.kind === kind && pos.has(e.source) && pos.has(e.target));
    if (!es.length) continue;
    const st = KIND_STYLE[kind];
    const x: (number | null)[] = [];
    const y: (number | null)[] = [];
    const size: number[] = [];
    for (const e of es) {
      const a = pos.get(e.source)!;
      const b = pos.get(e.target)!;
      const tip = along(a, b, 0.62);
      x.push(a[0], tip[0], b[0], null);
      y.push(a[1], tip[1], b[1], null);
      size.push(0, e.directed ? 11 : 0, 0, 0);
    }
    data.push({ type: "scatter", mode: "lines+markers", name: st.label, x, y, hoverinfo: "skip", legendgroup: kind, showlegend: false,
                line: { color: st.colour, width: st.width, dash: st.dash },
                marker: { symbol: "arrow", size, color: st.colour, angleref: "previous", opacity: 0.95 } });
    // an invisible marker in the middle of each edge carries its hover text
    const mid = es.map((e) => along(pos.get(e.source)!, pos.get(e.target)!, 0.5));
    data.push({ type: "scatter", mode: "markers", name: `${st.label} (links)`, x: mid.map((m) => m[0]), y: mid.map((m) => m[1]),
                marker: { size: 12, color: st.colour, opacity: 0 }, showlegend: false, legendgroup: kind,
                text: es.map((e) => `<b>${st.label}</b><br>${e.source.replace(/^P:/, "")} → ${e.target}<br>${e.label}`),
                hovertemplate: "%{text}<extra></extra>", customdata: es.map((e) => ({ edge: e.id })) });
  }

  // borrowers and customers: one trace per Early Warning band, so the legend key is the band
  const bands = ["critical", "high", "moderate", "low", "none"];
  const showAllLabels = nodes.length <= 24;
  for (const band of bands) {
    const ns = nodes.filter((n) => n.type !== "person" && n.ews_band === band);
    if (!ns.length) continue;
    data.push({
      type: "scatter", mode: "markers+text", name: BAND_LABEL[band], legendgroup: `band-${band}`, showlegend: false,
      x: ns.map((n) => n.x), y: ns.map((n) => n.y),
      text: ns.map((n) => (showAllLabels || n.is_focal || n.hop <= 1 ? trunc(n.name ?? n.id, 24) : "")),
      textposition: "bottom center", textfont: { size: 11, color: "#334155" },
      marker: { size: ns.map((n) => nodeSize(n.exposure, maxExp, nodes.length > 24)), color: BAND_COLOURS[band], opacity: 0.95,
                line: { color: ns.map((n) => (n.is_focal ? "#0f172a" : "#ffffff")), width: ns.map((n) => (n.is_focal ? 4 : 1.5)) } },
      hovertemplate: "%{customdata.hover}<extra></extra>",
      customdata: ns.map((n) => ({ id: n.id, href: n.href ?? "", type: n.type, focal: n.is_focal, hover: hoverNode(n) })),
    });
  }
  const people = nodes.filter((n) => n.type === "person");
  if (people.length) {
    data.push({ type: "scatter", mode: "markers+text", name: "Owner or director", legendgroup: "person", showlegend: false,
                x: people.map((n) => n.x), y: people.map((n) => n.y), text: people.map((n) => trunc(n.name, 20)),
                textposition: "bottom center", textfont: { size: 10, color: "#475569" },
                marker: { symbol: "diamond", size: 16, color: "#cbd5e1", line: { color: "#64748b", width: 2 } },
                hovertemplate: "%{customdata.hover}<extra></extra>",
                customdata: people.map((n) => ({ id: n.id, href: "", type: "person", focal: false, hover: hoverNode(n) })) });
  }
  return {
    data,
    layout: {
      showlegend: false, hovermode: "closest", dragmode: "pan",
      xaxis: { visible: false, range: [-1.25, 1.25], fixedrange: false, scaleanchor: "y" },
      yaxis: { visible: false, range: [-1.25, 1.25], fixedrange: false },
      margin: { l: 8, r: 8, t: 8, b: 8 },
    },
    shown: { nodes: nodes.length, edges: edges.length },
  };
}

/** What kinds are in this payload, in the order the legend shows them. */
export function kindsIn(g: GraphPayload): Kind[] {
  return KIND_ORDER.filter((k) => (g.legend[k]?.count ?? 0) > 0);
}
