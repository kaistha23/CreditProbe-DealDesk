/**
 * PLAN_R13 §I Session IC: types and pure formatting for the three network panels (event translator, contagion map,
 * employer exposure). No React here, so the node test runner covers it. Amounts arrive in SAR million.
 */

export type Severity = "mild" | "moderate" | "severe";
export type Tone = "neutral" | "positive" | "negative" | "warning";
export interface Tile { label: string; value: string; sub?: string; tone?: Tone; info?: string }
export interface Writer { headline: string; lines: string[] }
export interface Source { domain?: string; relation?: string; release?: string; period?: string; path?: string | null; label?: string }
export interface View { view: string; key: string; inputs_sha256: string; content_sha256?: string; path?: string; published: boolean }
export interface Calibration { source: "whatif_current" | "r13_s" | string; label: string; note: string; path?: string | null }

// ---------------------------------------------------------------- event translator

export type EventFamily = "oil" | "gdp" | "rates" | "red_sea" | "developer_delay" | "sector_downgrade";
export interface EventDriver { driver: string; label: string; value: number; unit: string; scope: string; assumption: string; basis: string }
export interface EventChannel { channel: string; borrowers: number; ead: number; d_ecl: number; to_stage2: number; to_stage3: number }
export interface CallRow {
  borrower_id: string; name: string; sector: string; channel: string; ead: number; d_ecl: number; to_stage2: number;
  to_stage3: number; ews_band: string | null; rating: string | null; reason: string; action: string; href: string;
  rm?: string | null; rm_id?: string | null; branch?: string | null;
}
export interface EventResult {
  period: string; severity: Severity;
  event: { family: EventFamily; label: string; severity: Severity; params: Record<string, unknown>; text: string; parsed: string[] };
  calibration: Calibration; drivers: EventDriver[]; assumptions: string[];
  impact: {
    ecl_before: number; ecl_after: number; ecl_change: number; ecl_change_pct: number | null;
    stage2_before_n: number; stage2_after_n: number; stage2_ead_before: number; stage2_ead_after: number;
    to_stage2_n: number; to_stage3_n: number; facilities: number; ead: number;
  };
  channels: EventChannel[]; by_sector: { sector: string; ead: number; d_ecl: number; to_stage2: number }[];
  borrowers: (CallRow & { share_pct: number | null; notches: number | null; ecl_before: number; ecl_after: number })[];
  affected: { direct: number; network: number; with_ecl_change: number };
  employers: { retail_workforce: { customers: number; accounts: number; exposure: number; stage2_exposure: number; month: string } };
  call_list: CallRow[]; limits: string[]; lineage: Source[]; text: Writer; view?: View; money_unit: string;
  deal_desk?: { project_id: string; project: string; proposal_id: string; contractor_id: string; contractor: string | null; due: number; retention: number; backlog: number; lg_outstanding: number; payment_delay_days: number | null; rm: string | null }[];
}
export interface EventCatalogue {
  families: { family: EventFamily; label: string; example: string; params: Record<string, string> }[];
  severities: Severity[]; calibration: Calibration;
}
export interface EventRequest { text?: string; family?: EventFamily; params?: Record<string, unknown>; severity?: Severity; period?: string }

// ---------------------------------------------------------------- contagion

export type ContagionChannel = "guarantee" | "group" | "collateral" | "supplier" | "customer" | "employer";
export interface ContagionName {
  borrower_id: string; name: string; sector: string; rating: string | null; ews_band: string | null;
  channels: ContagionChannel[]; why: string; exposure: number; ead: number; at_risk: number; notches: number;
  d_ecl: number; to_stage2: number; to_stage3: number; href: string;
}
export interface NetNode { id: string; name: string; kind: ContagionChannel | "focal"; x: number; y: number; exposure: number; at_risk?: number; d_ecl: number; ews_band: string | null; channels?: string[] }
export interface NetEdge { source: string; target: string; kind: ContagionChannel; at_risk: number; label: string }
export interface ContagionResult {
  period: string; severity: Severity;
  focal: { borrower_id: string; name: string; sector: string; rating: string | null; ead: number; ecl: number; ews_band: string | null; group: string | null };
  totals: { names: number; exposure: number; at_risk: number; d_ecl_second: number; d_ecl_focal: number; to_stage2: number; to_stage3: number; focal_ead: number; total_exposure_with_focal: number };
  channels: { channel: ContagionChannel; label: string; names: number; exposure: number; at_risk: number; d_ecl: number }[];
  names: ContagionName[];
  network: { nodes: NetNode[]; edges: NetEdge[]; kinds: Record<string, string>; drawn: number; available: number };
  limits: string[]; calibration: Calibration; lineage: Source[]; text: Writer; view?: View; money_unit: string;
  /** R14 G: the registered row in Data Domains (network_intel · net_contagion_view) when the focal name is published. */
  data_domains?: DataDomainsRef | null;
}

/** R14 G: a registered Data Domains row behind a network answer. */
export interface DataDomainsRef { source?: Source; published_at?: string; same_as_published?: boolean; note: string }

// ---------------------------------------------------------------- employer

export interface ContractorRow {
  borrower_id: string; name: string; sector: string; is_contractor: boolean; ead: number; funded: number; non_funded: number;
  project_finance: number; ecl: number; stage: number | null; revenue_share_pct: number; annual_paid_sar_mn: number;
  attributable: number; rating: string | null; ews_band: string | null; dependence: "high" | "material" | "low"; href: string;
}
export interface ProjectRow {
  project_id: string; project: string; proposal_id: string; contractor_id: string; contractor: string | null; status: string;
  contract_value: number; backlog: number; due: number; retention: number; payment_delay_days: number | null;
  pending_certs: number | null; last_cert_no: number | null; lg_outstanding: number; funded_outstanding: number; lg_products: string[];
}
export interface EmployerResult {
  period: string;
  employer: { name: string; borrower_id: string | null; entity_id: string | null; sector: string | null; rating: string | null; ews_band: string | null; credit_status: string | null; bureau: Record<string, unknown> | null };
  totals: { contractors: number; book_contractors: number; exposure: number; non_funded: number; attributable: number; deal_desk_outstanding: number; deal_desk_proposed: number; own_exposure: number; lg_outstanding: number; due: number; retention: number; in_early_warning: number; ews_exposure: number; high_dependence: number };
  appetite: { label: string; basis: string; metric: string; value: number; appetite: number; trigger: number; limit: number; utilisation_pct: number; status: string;
              deal_desk_dependence: { contractor_id: string; backlog_share: number | null; backlog: number; guide: number; flag: boolean }[] };
  contractors: ContractorRow[]; projects: ProjectRow[]; by_sector: { sector: string; names: number; ead: number; attributable: number }[];
  limits: string[]; lineage: Source[]; text: Writer; view?: View; money_unit: string;
  /** R14 G: the registered row (network_intel · net_employer_view) when the employer is published. */
  data_domains?: DataDomainsRef | null;
}
export interface EmployerRanking {
  period: string;
  rows: { employer_id: string; name: string; sector: string; contractors: number; contractor_ead: number; attributable: number; max_share: number; own_ead: number | null; combined: number; status: string; utilisation_pct: number }[];
  appetite: { label: string; appetite: number; trigger: number; limit: number; basis: string };
  deal_desk_employers: { entity_id: string; name: string; credit_status: string | null }[];
  method: string; money_unit: string;
}

// ---------------------------------------------------------------- formatting

const MINUS = "−";

export function sar(x: number | null | undefined, dp = 1): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "–";
  return `SAR ${x.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp })}m`;
}

export function dsar(x: number | null | undefined, dp = 1): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "–";
  const body = Math.abs(x).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
  return `${x < 0 ? MINUS : "+"}SAR ${body}m`;
}

export function pct(x: number | null | undefined, dp = 1, signed = false): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "–";
  const s = Math.abs(x).toFixed(dp);
  return `${signed ? (x < 0 ? MINUS : "+") : x < 0 ? MINUS : ""}${s}%`;
}

export function signedInt(x: number): string {
  return `${x < 0 ? MINUS : "+"}${Math.abs(x).toLocaleString("en-US")}`;
}

export const CHANNEL_LABEL: Record<string, string> = {
  direct: "Direct", contractor: "Contractor of the developer", supplier: "Supplier", customer: "Buyer", macro: "Sector beta",
  guarantee: "Guaranteed by it", group: "Same group", collateral: "Shared collateral", employer: "Same project employer",
  focal: "Failed name",
};

/** House chart colours per channel (CSS variables; the Plot wrapper resolves them against the live theme). */
export const CHANNEL_COLOUR: Record<string, string> = {
  focal: "var(--ipm-negative)", guarantee: "var(--ipm-chart-1)", group: "var(--ipm-chart-2)", collateral: "var(--ipm-chart-3)",
  supplier: "var(--ipm-chart-4)", customer: "var(--ipm-chart-5)", employer: "var(--ipm-chart-6)",
};

export const FAMILY_PICKS: { family: EventFamily; label: string; text: string }[] = [
  { family: "oil", label: "Oil falls", text: "What if oil falls 30% this morning?" },
  { family: "red_sea", label: "Red Sea disruption", text: "Red Sea shipping disruption" },
  { family: "developer_delay", label: "Developer delays payments", text: "" },
  { family: "sector_downgrade", label: "Sector downgrade", text: "" },
];

export function calibrationLine(c: Calibration): string {
  return c.source === "r13_s" ? `Severity: ${c.label} (Data Domains).` : `Severity: ${c.label}; §S calibration not merged yet.`;
}

export function eventTiles(r: EventResult): Tile[] {
  const i = r.impact;
  const s2 = i.stage2_after_n - i.stage2_before_n;
  const calls = r.call_list.length;
  return [
    { label: "ECL hit", value: dsar(i.ecl_change), sub: `${pct(i.ecl_change_pct, 2, true)} to ${sar(i.ecl_after, 0)}`,
      tone: i.ecl_change > 0 ? "negative" : "neutral", info: "What-If engine (Delta method), every facility before and after the event's drivers." },
    { label: "Stage 2 facilities", value: signedInt(s2), sub: `${dsar(i.stage2_ead_after - i.stage2_ead_before, 0)} EAD · ${i.to_stage3_n} default`,
      tone: s2 > 0 || i.to_stage3_n > 0 ? "warning" : "neutral", info: "Re-staged by the What-If rules: rating, days past due, notches from origination and the PD test." },
    { label: "Borrowers hit", value: r.affected.with_ecl_change.toLocaleString("en-US"),
      sub: `${r.affected.direct} direct · ${r.affected.network} linked`, info: "Borrowers whose ECL rises; direct and second-ring through supplier and buyer links." },
    { label: "Call today", value: String(calls), sub: calls ? r.call_list[0].name : "no one", tone: calls ? "warning" : "neutral",
      info: "Ranked by a stage move, then the ECL change, then exposure." },
  ];
}

export function contagionTiles(r: ContagionResult): Tile[] {
  const t = r.totals;
  return [
    { label: "Linked names", value: t.names.toLocaleString("en-US"), sub: `${sar(t.exposure, 0)} exposure`, info: "Book borrowers one step from the failed name through any channel." },
    { label: "At risk", value: sar(t.at_risk), sub: `${pct(t.exposure ? (100 * t.at_risk) / t.exposure : null, 0)} of linked exposure`, tone: "warning",
      info: "Exposure times each channel's transmission share (guaranteed amount, control, revenue or purchase share, collateral fall)." },
    { label: "Second-order ECL", value: dsar(t.d_ecl_second), sub: `own ${dsar(t.d_ecl_focal)}`, tone: t.d_ecl_second > 0 ? "negative" : "neutral",
      info: "What-If engine: the failed name defaults and the channels transmit, in one run." },
    { label: "Stage moves", value: `${t.to_stage2} / ${t.to_stage3}`, sub: "to Stage 2 / to default", tone: t.to_stage3 ? "negative" : t.to_stage2 ? "warning" : "neutral" },
  ];
}

export function employerTiles(r: EmployerResult): Tile[] {
  const t = r.totals;
  const a = r.appetite;
  const tone: Tone = a.status === "within appetite" ? "positive" : a.status === "over appetite" ? "warning" : "negative";
  return [
    { label: "Via contractors", value: sar(t.exposure, 0), sub: `${t.contractors} paid by it`, info: "EAD of every borrower the employer pays (book) plus Deal Desk project LGs and funded lines outstanding." },
    { label: "Attributable", value: sar(t.attributable), sub: "EAD × share it pays", info: r.limits[1] },
    { label: "Own exposure", value: sar(t.own_exposure), sub: r.employer.borrower_id ?? "not in the book" },
    { label: "Vs appetite", value: pct(a.utilisation_pct, 0), sub: a.status, tone, info: `${a.metric} against the ${sar(a.limit, 0)} limit. ${a.basis}` },
  ];
}

/** Plotly traces for the contagion network: one edge trace per channel (legend toggles a channel), one node trace. */
export function networkFigure(r: ContagionResult): { data: Record<string, unknown>[]; layout: Record<string, unknown> } {
  const pos = new Map(r.network.nodes.map((n) => [n.id, n]));
  const kinds = Array.from(new Set(r.network.edges.map((e) => e.kind)));
  const data: Record<string, unknown>[] = kinds.map((k) => {
    const xs: (number | null)[] = [];
    const ys: (number | null)[] = [];
    for (const e of r.network.edges.filter((x) => x.kind === k)) {
      const a = pos.get(e.source);
      const b = pos.get(e.target);
      if (!a || !b) continue;
      xs.push(a.x, b.x, null);
      ys.push(a.y, b.y, null);
    }
    return { type: "scatter", mode: "lines", x: xs, y: ys, name: CHANNEL_LABEL[k] ?? k, hoverinfo: "skip",
             line: { color: CHANNEL_COLOUR[k] ?? "var(--ipm-border-strong)", width: 1.4 }, legendgroup: k };
  });
  const maxExp = Math.max(1, ...r.network.nodes.map((n) => n.exposure || 0));
  const nodes = r.network.nodes;
  data.push({
    type: "scatter", mode: "markers+text", showlegend: false,
    x: nodes.map((n) => n.x), y: nodes.map((n) => n.y),
    text: nodes.map((n) => (n.kind === "focal" || n.d_ecl > 0.5 ? short(n.name) : "")), textposition: "top center",
    textfont: { size: 10 },
    marker: { size: nodes.map((n) => 8 + 22 * Math.sqrt((n.exposure || 0) / maxExp)),
              color: nodes.map((n) => CHANNEL_COLOUR[n.kind] ?? "var(--ipm-chart-8)"),
              line: { width: nodes.map((n) => (n.kind === "focal" ? 2 : 0.5)), color: "var(--ipm-surface)" } },
    customdata: nodes.map((n) => n.id),
    hovertext: nodes.map((n) => `${n.name} (${n.id})<br>${CHANNEL_LABEL[n.kind] ?? n.kind}<br>Exposure ${sar(n.exposure)}`
      + (n.at_risk !== undefined ? ` · at risk ${sar(n.at_risk)}` : "") + `<br>ECL ${dsar(n.d_ecl, 2)}`),
    hoverinfo: "text",
  });
  const axis = { visible: false, range: [-1.25, 1.25], zeroline: false, showgrid: false };
  return { data, layout: { xaxis: axis, yaxis: { ...axis, scaleanchor: "x" }, margin: { l: 8, r: 8, t: 8, b: 8 },
                           legend: { orientation: "h", y: -0.04 }, hovermode: "closest" } };
}

export function short(name: string, n = 22): string {
  return name.length > n ? `${name.slice(0, n - 1)}…` : name;
}

export function sourceLine(src: Source[]): string {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const s of src) {
    const k = `${s.domain ?? ""} · ${s.relation ?? ""}`;
    if (!seen.has(k)) { seen.add(k); out.push(k); }
  }
  return out.join("; ");
}

export function bandTone(band: string | null | undefined): Tone {
  return band === "critical" || band === "high" ? "negative" : band === "moderate" ? "warning" : "neutral";
}
