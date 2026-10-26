/**
 * R12 Session C (I24): the group, governance, conduct and SWOT payloads of /api/v1/dealdesk/proposals/{id}/group/*,
 * typed, plus the pure helpers the panels use (tested in model.test.ts). No imports, so node --test runs it as is.
 */

export interface Source { domain: string | null; relation: string; keys: Record<string, unknown>; field?: string | null; observed?: unknown }
export interface Lineage { relation: string; domain: string | null; available: boolean; via: string; rows: number; filters: Record<string, unknown>[] }

export interface Node {
  borrower_id: string; name: string; link: string; role?: string | null; ownership_pct?: number | null; ead: number;
  rating?: string | null; status: string; ews_band?: string; href?: string | null; activity?: string | null; country?: string | null;
}
export interface Structure {
  group_id: string | null; group_name: string | null; standalone: boolean; members: number; member_ids: string[];
  focal: { borrower_id: string | null; name: string; in_book: boolean; role?: string | null; ownership_pct?: number | null;
           licence_no?: string | null; incorporation_date?: string | null; legal_status?: string | null; activity?: string | null; staff_count?: number | null };
  parent: Node | null; subsidiaries: Node[]; sisters: Node[]; source: Source[];
}
export interface Shareholder {
  name: string; pct: number | null; indirect_pct?: number | null; ubo: boolean; nationality?: string | null; kind: string;
  via?: string; since?: string | null; nominee?: boolean;
}
export interface BoardRow {
  person_id: string | null; name: string; roles: string[]; key_person?: boolean; other_directorships?: string | null;
  other_borrowers: { borrower_id: string; name: string; status: string; ews_band: string; ead: number; href?: string | null }[];
  linked_to_stressed: string[];
}
export interface Connected {
  borrower_id: string; name: string; links: string[]; ead: number; rating?: string | null; status: string; classified: boolean;
  in_arrears: boolean; in_litigation: boolean; ews_band: string; max_dpd_4q: number; classified_basis?: string[]; note?: string | null;
  href?: string | null;
}
export interface GroupFacts {
  proposal_id: string; mode: "book" | "entity"; obligor: { id: string; name: string; existing: boolean }; as_of: string;
  structure: Structure;
  shareholders: { rows: Shareholder[]; identified_pct: number; ubo_count: number; ubo_identified: boolean; provided_by: string; source: Source[] };
  board: { rows: BoardRow[]; people: number; linked_people: number; source: Source[] };
  insiders: { rows: { party: string; entity?: string | null; link: string; role?: string | null; relationship?: string | null; pct?: number | null;
                      disclosed?: boolean; detected_by?: string | null; detail?: string | null }[]; count: number; provided: boolean; note?: string };
  ownership_changes: { rows: { date: string; entity?: string; holder?: string; from?: string | null; to?: string | null; pct?: number | null; kind?: string | null;
                               disclosed?: boolean; detail?: string | null }[]; count: number; lookback: string };
  shared_collateral: { assets: { collateral_id: string; type: string; market_value: number | null; total_pct: number | null; over_pledged: boolean;
                                 claims: { borrower_id: string; name: string; is_self: boolean; allocation_pct?: number | null }[] }[]; count: number };
  guarantees: { rows: { direction: string; guarantor_id: string; guarantor?: string; amount: number | null; basis?: string | null; perfection?: string | null }[];
                unperfected: { guarantor_id: string; amount: number }[] };
  connected_parties: { rows: Connected[]; count: number; classified: number; in_arrears: number; in_litigation: number; adverse: string[]; adverse_ead: number };
}
export interface Doa { level: string; rank: number; reasons: string[] }
export interface IncreaseAsk {
  kind: "increase_cap" | "policy_exception" | "increase_cap_requested"; from_sar_mn: number; to_sar_mn: number; increase_sar_mn: number;
  increase_pct: number | null; fits_without_increase_ead_sar_mn: number; doa: Doa; text: string; alternative: string;
}
export interface CapTest {
  group_name: string | null; before_ead: number; deal_ead_y1: number; after_ead: number; binding_limit: number; binding: string;
  headroom_after: number; status: "within" | "watch" | "breach"; utilisation_pct: number | null; basis: string;
  connected_group_limit: { limit_sar_mn: number; basis: string };
  approved_cap: { limit_sar_mn: number; approved_by: string | null; approved_on: string | null; committee_ref: string | null } | null;
  members: { borrower_id: string; name: string; ead: number; limit: number; funded_limit: number; proposed_limit?: number; is_self: boolean }[];
  increase_ask: IncreaseAsk | null; cap_asked_sar_mn?: number | null;
}
export interface Conduct {
  headline: string; existing: boolean;
  relationship: { since: string | null; accounts: number; years: number | null };
  utilisation: { limits_sar_mn: number; drawn_sar_mn: number; utilisation_pct: number | null; over_90_4q: string[]; excess_days_12m: number;
                 facilities: { facility_id: string; product: string; limit: number; drawn: number; utilisation_pct: number | null; avg_4q_pct: number | null }[] };
  past_dues: { quarters: { quarter: string; max_dpd: number; past_due_facilities: number }[]; quarters_past_due_8q: number; max_dpd_8q: number;
               max_dpd_4q: number; last_past_due: string | null };
  turnover: { credit_turnover_12m_sar_mn: number | null; credit_turnover_prev_12m_sar_mn: number | null; growth_pct: number | null; to_limits_x: number | null;
              routing_required_x: number | null; routing_actual_x: number | null; routing_compliant: boolean | null; routing_achieved_pct: number | null;
              months: { month: string; credit_turnover_sar_mn: number | null; avg_balance_sar_mn: number | null; cheques_returned_count: number }[] };
  returned_cheques: { count_12m: number; amount_12m_sar_mn: number; months_with_returns: number; reasons: string[];
                      dates: { month: string; count: number; amount: number | null; reason: string | null }[] };
  bureau: { trend: string; max_external_dpd_4q: number | null; enquiries_4q: number | null;
            quarters: { quarter: string; external_exposure_sar_mn: number | null; external_dpd_days: number | null; enquiries: number | null }[];
            entity_reports: { entity: string; role?: string | null; outstanding_sar_mn?: number | null; overdue_sar_mn?: number | null; score?: number | null;
                              court_cases?: number | null; provided: boolean; not_provided_reason?: string | null }[] };
  source: Source[];
}
export interface Flag {
  code: string; family: "governance" | "conduct"; severity: "high" | "medium" | "low" | "info"; notch: number; title: string; detail: string;
  review_point_label: string; finding_id: string; evidence: Source[];
  condition: { condition_id: string; kind: string; owner: string; due: string; text: string };
}
export interface Overlay { base_rating: string; overlaid_rating: string; notches: number; notches_raw: number; capped: boolean; cap: number; text: string;
                           reasons: { code: string; title: string; notch: number; finding_id: string }[]; basis: string }
export interface Governance {
  flags: Flag[]; overlay: Overlay; counts: { governance: number; conduct: number; high: number }; rules_version: string;
  conditions: { condition_id: string; kind: string; owner: string; due: string; text: string; source_finding: string }[];
}
export type Quadrant = "strength" | "weakness" | "opportunity" | "threat";
export interface SwotPoint { id: string; quadrant: Quadrant; kind: "financial" | "qualitative"; theme: string; text: string; evidence: Source[];
                             link: { type?: string; id?: string; step?: string } }
export interface Swot { points: SwotPoint[]; counts: Record<Quadrant, number>; summary: string; writer: string }
export interface MitigantRow {
  swot_id: string; quadrant: Quadrant; theme: string; weakness: string; status: "answered by the structure" | "answered by a condition" | "open";
  structure: { lever: string; text: string }[]; conditions: { condition_id: string; text: string; kind: string; due: string }[];
  suggestion: string | null; link: { type?: string; id?: string; step?: string };
}
export interface Mitigants { structure_label: string; rows: MitigantRow[]; counts: { total: number; structure: number; condition: number; open: number };
                             headline: string }
export interface GroupAll {
  proposal_id: string; as_of: string; facts: GroupFacts; cap_test: CapTest | null; conduct: Conduct; governance: Governance; swot: Swot;
  mitigants: Mitigants; lineage: Lineage[]; not_published: string[]; gaps: string[];
}

// ---------------------------------------------------------------- helpers

export type Tone = "positive" | "negative" | "warning" | "neutral" | "accent";

const DASH = "–";
const ok = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const fx = (v: number, dp: number) => v.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });

/** SAR millions: "SAR 554.2m", "SAR 4.50m", "SAR 1.25bn". */
export function sarm(v: number | null | undefined): string {
  if (!ok(v)) return DASH;
  const a = Math.abs(v);
  if (a >= 1000) return `SAR ${fx(v / 1000, 2)}bn`;
  return `SAR ${fx(v, a < 10 ? 2 : 1)}m`;
}

/** A percentage already in points: "111%", "8.5%". */
export function pts(v: number | null | undefined, dp?: number): string {
  if (!ok(v)) return DASH;
  return `${fx(v, dp ?? (Math.abs(v) >= 100 ? 0 : 1))}%`;
}

export function statusTone(status: string | null | undefined): Tone {
  switch (status) {
    case "classified": case "in litigation": case "breach": case "high": case "critical": case "deteriorating": return "negative";
    case "in arrears": case "watchlist": case "watch": case "medium": case "moderate": case "rising exposure": return "warning";
    case "performing": case "within": case "stable": case "low": return "positive";
    default: return "neutral";
  }
}

export function severityTone(sev: string): Tone {
  return sev === "high" || sev === "critical" ? "negative" : sev === "medium" ? "warning" : "neutral";
}

export function mitigantTone(status: MitigantRow["status"]): Tone {
  return status === "open" ? "negative" : status === "answered by a condition" ? "warning" : "positive";
}

export const QUADRANTS: { key: Quadrant; label: string; tone: Tone }[] = [
  { key: "strength", label: "Strengths", tone: "positive" },
  { key: "weakness", label: "Weaknesses", tone: "negative" },
  { key: "opportunity", label: "Opportunities", tone: "accent" },
  { key: "threat", label: "Threats", tone: "warning" },
];

/** "deposits · dep_month · obligor_id=CB01338": where a figure comes from, for (i) and Trace. */
export function evidenceLine(s: Source): string {
  const keys = Object.entries(s.keys ?? {})
    .map(([k, v]) => `${k}=${Array.isArray(v) ? (v.length > 3 ? `${v.slice(0, 3).join(",")}…(${v.length})` : v.join(",")) : String(v)}`)
    .join("; ");
  return [s.domain ?? "data", s.relation, keys].filter(Boolean).join(" · ");
}

/** The step a SWOT point or finding links to, as a label. */
export function stepLabel(step: string | undefined): string {
  const m: Record<string, string> = { analysis: "Analysis", review: "Review", structure: "Structure", stress: "Stress", proposal: "Proposal" };
  return step ? m[step] ?? step : "";
}

/** The answer line over the group panel: exposure against the binding limit, then the governance verdict. */
export function capLine(c: CapTest | null): string {
  if (!c) return "Group cap test not available for this deal.";
  const lim = c.binding === "approved cap" ? "the approved group cap" : "the connected group limit";
  const verdict = c.status === "breach" ? "breach" : c.status === "watch" ? "within, above 90%" : "within";
  return `Group exposure ${sarm(c.after_ead)} after the deal against ${lim} of ${sarm(c.binding_limit)} (${pts(c.utilisation_pct)}): ${verdict}.`;
}

export function structureLine(f: GroupFacts): string {
  const s = f.structure;
  if (s.standalone && !s.parent && !s.subsidiaries.length) return `${f.obligor.name}: standalone, no group in the bank's records.`;
  const parts = [`${s.group_name ?? "Group"}: ${s.members} member${s.members === 1 ? "" : "s"}`];
  if (s.parent) parts.push(`parent ${s.parent.name}${ok(s.parent.ownership_pct) ? ` (${pts(s.parent.ownership_pct)})` : ""}`);
  if (s.subsidiaries.length) parts.push(`${s.subsidiaries.length} subsidiar${s.subsidiaries.length === 1 ? "y" : "ies"}`);
  if (s.sisters.length) parts.push(`${s.sisters.length} sister compan${s.sisters.length === 1 ? "y" : "ies"}`);
  const cp = f.connected_parties;
  const bad = [cp.classified && `${cp.classified} classified`, cp.in_litigation && `${cp.in_litigation} in litigation`,
               cp.in_arrears && `${cp.in_arrears} in arrears`].filter(Boolean);
  return `${parts.join(", ")}. ${bad.length ? `Connected parties: ${bad.join(", ")}.` : "No connected party classified, in arrears or in litigation."}`;
}

export function ownershipText(r: Shareholder): string {
  if (ok(r.pct)) return pts(r.pct);
  if (ok(r.indirect_pct)) return `${pts(r.indirect_pct)} via ${r.via ?? "a holding"}`;
  return DASH;
}

/** Group points by quadrant, keeping the server's order (financial first within a quadrant). */
export function byQuadrant(points: SwotPoint[]): Record<Quadrant, SwotPoint[]> {
  const out: Record<Quadrant, SwotPoint[]> = { strength: [], weakness: [], opportunity: [], threat: [] };
  for (const p of points) out[p.quadrant].push(p);
  return out;
}

export function conductKpis(c: Conduct): { label: string; value: string; sub: string; tone: Tone }[] {
  const t = c.turnover, rc = c.returned_cheques, u = c.utilisation, pd = c.past_dues;
  return [
    { label: "Turnover / limits", value: ok(t.to_limits_x) ? `${fx(t.to_limits_x, 2)}x` : DASH,
      sub: `${sarm(t.credit_turnover_12m_sar_mn)} in 12m${ok(t.credit_turnover_prev_12m_sar_mn) ? ` (PY ${sarm(t.credit_turnover_prev_12m_sar_mn)})` : ""}`,
      tone: ok(t.growth_pct) && t.growth_pct <= -20 ? "negative" : "neutral" },
    { label: "Routing", value: ok(t.routing_achieved_pct) ? pts(t.routing_achieved_pct, 0) : DASH,
      sub: ok(t.routing_required_x) ? `${fx(t.routing_actual_x ?? 0, 2)}x of ${fx(t.routing_required_x, 1)}x required` : "no undertaking",
      tone: t.routing_compliant === false ? "negative" : t.routing_compliant ? "positive" : "neutral" },
    { label: "Returned cheques", value: String(rc.count_12m), sub: `${sarm(rc.amount_12m_sar_mn)} in 12 months`,
      tone: rc.count_12m >= 3 ? "negative" : rc.count_12m > 0 ? "warning" : "positive" },
    { label: "Utilisation", value: pts(u.utilisation_pct, 0), sub: `${sarm(u.drawn_sar_mn)} of ${sarm(u.limits_sar_mn)}`,
      tone: u.over_90_4q.length ? "negative" : "neutral" },
    { label: "Past dues", value: pd.max_dpd_8q ? `${pd.max_dpd_8q} days` : "None",
      sub: `${pd.quarters_past_due_8q} of ${pd.quarters.length} quarters`, tone: pd.max_dpd_4q >= 30 ? "negative" : pd.max_dpd_8q ? "warning" : "positive" },
    { label: "Bureau trend", value: c.bureau.trend.charAt(0).toUpperCase() + c.bureau.trend.slice(1),
      sub: ok(c.bureau.max_external_dpd_4q) ? `max ${c.bureau.max_external_dpd_4q} days past due` : "", tone: statusTone(c.bureau.trend) },
  ];
}
