/**
 * PLAN_R9: the CreditProbe Intelligence Packs.
 *
 * CreditProbe is the system; the packs are the product. One definition, read by
 * the "Powered by" strip on every answer, the Intelligence Library ("what you
 * license"), the Workspace briefing and the Cockpit's self-description, so a
 * pack can never be named one way in one place and another way elsewhere.
 *
 * Pure data and pure functions: no React, so node --test covers it directly.
 */

export type PackId = "P1" | "P2" | "P3" | "P4" | "P5" | "P6" | "P7";

export type Confidence = "high" | "medium" | "low";

export interface PackRule {
  /** Our rule ID, stable across versions, e.g. "P2-UTP-03". */
  id: string;
  /** What the rule decides, in one line. */
  title: string;
  /** The metric or test it computes. */
  metric: string;
  /** The threshold or trigger. */
  threshold: string;
  /** The regulatory source it implements. */
  source: string;
}

export interface IntelligencePack {
  id: PackId;
  name: string;
  /** One line: what the pack knows. */
  knows: string;
  version: string;
  /** Where it shows up, with the route that opens it. */
  usedIn: { label: string; href: string }[];
  rules: PackRule[];
}

const CRM = "CBUAE Credit Risk Management Regulation and Standards (Circular 29/2018)";
const IFRS9 = "CBUAE IFRS 9 Implementation Guidance";

export const INTELLIGENCE_PACKS: readonly IntelligencePack[] = [
  {
    id: "P1",
    name: "CBUAE CRM Intelligence",
    knows: "Every CBUAE credit risk obligation as a metric, a rule and a threshold, with its article.",
    version: "1.4.0",
    usedIn: [
      { label: "Lenses", href: "/lenses" },
      { label: "Policy Docs", href: "/policy-docs" },
      { label: "Cockpit breach checks", href: "/" },
    ],
    rules: [
      { id: "P1-CON-01", title: "Single obligor and group concentration", metric: "Exposure to one obligor or group / Tier 1 capital", threshold: "Limit set by the large exposure rules; alert at 80% of the limit", source: `${CRM}, credit concentration` },
      { id: "P1-REL-02", title: "Related-party lending", metric: "Related-party exposure / Tier 1 capital", threshold: "Board-approved related-party limits; every breach escalated", source: `${CRM}, related parties` },
      { id: "P1-REV-03", title: "Annual credit review", metric: "Days since last credit review per obligor", threshold: "Overdue after 12 months (6 for watch-list names)", source: `${CRM}, credit review` },
      { id: "P1-COL-04", title: "Collateral valuation currency", metric: "Days since last valuation per collateral item", threshold: "Revalue at least annually; real estate per the Standards", source: `${CRM}, collateral management` },
    ],
  },
  {
    id: "P2",
    name: "SICR & Default Intelligence",
    knows: "CBUAE SICR and unlikeliness-to-pay indicators, automated with evidence and routing.",
    version: "1.2.0",
    usedIn: [{ label: "Borrower 360", href: "/borrower-360" }],
    rules: [
      { id: "P2-SICR-01", title: "30 days past due backstop", metric: "Days past due", threshold: "> 30 DPD moves to Stage 2", source: `${IFRS9}, SICR` },
      { id: "P2-SICR-02", title: "Rating downgrade", metric: "Notches down since origination", threshold: "3 notches or more, or into the watch grades", source: `${IFRS9}, SICR` },
      { id: "P2-UTP-03", title: "Unlikeliness to pay", metric: "UTP indicators present (restructuring, covenant breach, legal action)", threshold: "Any hard indicator routes to Stage 3 review", source: `${CRM}, classification of credit facilities` },
      { id: "P2-DEF-04", title: "90 days past due default", metric: "Days past due", threshold: "> 90 DPD is default (Stage 3)", source: `${CRM}, non-performing classification` },
    ],
  },
  {
    id: "P3",
    name: "Early Warning → ECL Intelligence",
    knows: "PD by early warning bucket, and the ECL if the warnings come true.",
    version: "1.1.0",
    usedIn: [
      { label: "Early Warning", href: "/early-warning" },
      { label: "What-If", href: "/what-if" },
    ],
    rules: [
      { id: "P3-EWS-01", title: "Warning bucket calibration", metric: "Observed 12-month default rate by EWS bucket", threshold: "Critical, High, Medium, Low buckets recalibrated each quarter", source: `${CRM}, early warning systems` },
      { id: "P3-ECL-02", title: "ECL if warnings come true", metric: "ECL with Critical and High names moved to Stage 2 or 3", threshold: "Reported beside the booked ECL", source: `${IFRS9}, forward-looking information` },
    ],
  },
  {
    id: "P4",
    name: "Accepted Risk Intelligence",
    knows: "Concerns accepted at approval become dated watch items that escalate when they worsen.",
    version: "1.0.0",
    usedIn: [
      { label: "Early Warning (accepted-risk watch)", href: "/early-warning" },
      { label: "Workspace", href: "/workspace" },
    ],
    rules: [
      { id: "P4-ACC-01", title: "Accepted concern becomes a watch item", metric: "Condition, owner and review date captured at approval", threshold: "Every accepted concern is dated", source: `${CRM}, credit approval` },
      { id: "P4-ESC-02", title: "Escalate when it worsens", metric: "Change in the watched metric since approval", threshold: "Breach of the accepted level escalates to the approver", source: `${CRM}, credit monitoring` },
    ],
  },
  {
    id: "P5",
    name: "Network Intelligence",
    knows: "Group, sponsor, related-party and counterparty links, and cross-default.",
    version: "1.1.0",
    usedIn: [{ label: "Borrower 360 graph", href: "/borrower-360" }],
    rules: [
      { id: "P5-GRP-01", title: "Connected counterparties", metric: "Ownership, control and economic dependence links", threshold: "Linked names are treated as one group", source: `${CRM}, connected counterparties` },
      { id: "P5-XDF-02", title: "Cross-default", metric: "Default or UTP on any linked name", threshold: "Flags every facility in the group for review", source: `${CRM}, classification of credit facilities` },
    ],
  },
  {
    id: "P6",
    name: "ECL Diagnostics Intelligence",
    knows: "What moved ECL, input errors (rerun or not), and coverage against CBUAE floors.",
    version: "1.2.0",
    usedIn: [
      { label: "Cockpit", href: "/" },
      { label: "What-If", href: "/what-if" },
    ],
    rules: [
      { id: "P6-MOV-01", title: "ECL movement attribution", metric: "ECL change split by new business, stage transfers, PD/LGD and write-offs", threshold: "Explains 100% of the movement", source: `${IFRS9}, disclosures` },
      { id: "P6-ERR-02", title: "Input error check", metric: "Missing or out-of-range PD, LGD, EAD and staging inputs", threshold: "Material errors recommend a rerun", source: `${IFRS9}, governance` },
      { id: "P6-FLR-03", title: "Coverage against floors", metric: "Provision coverage by stage", threshold: "Compared with the CBUAE minimum coverage floors", source: `${CRM}, provisioning` },
    ],
  },
  {
    id: "P7",
    name: "Proposal & Regulatory Response Intelligence",
    knows: "Proposal review and counter-proposals, auditor and CBUAE query answers, and BRF mapping.",
    version: "1.0.0",
    usedIn: [
      { label: "Deal Desk", href: "/deal-desk" },
      { label: "Cockpit (auditor and CBUAE queries)", href: "/" },
      { label: "BRF", href: "/brf" },
    ],
    rules: [
      { id: "P7-PRO-01", title: "Proposal review", metric: "Pricing, structure and covenants against policy and hurdle", threshold: "Below hurdle or outside policy produces a counter-proposal", source: `${CRM}, credit approval` },
      { id: "P7-QRY-02", title: "Query answer", metric: "Auditor or CBUAE query answered from the books with evidence", threshold: "Every figure carries its Trace", source: `${CRM}, reporting` },
      { id: "P7-BRF-03", title: "BRF mapping", metric: "Banking Return Form cells mapped to the books", threshold: "Every cell reconciles to its source", source: "CBUAE Banking Return Forms" },
    ],
  },
];

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

export function findPack(id: string | undefined | null): IntelligencePack | undefined {
  if (!id) return undefined;
  const key = id.trim().toUpperCase();
  return INTELLIGENCE_PACKS.find((p) => p.id === key);
}

export function findRule(ruleId: string | undefined | null): { pack: IntelligencePack; rule: PackRule } | undefined {
  if (!ruleId) return undefined;
  const key = ruleId.trim().toUpperCase();
  for (const pack of INTELLIGENCE_PACKS) {
    const rule = pack.rules.find((r) => r.id === key);
    if (rule) return { pack, rule };
  }
  return undefined;
}

/** "P2 SICR & Default Intelligence" — how a pack is named on screen. */
export function packTitle(id: string): string {
  const pack = findPack(id);
  return pack ? `${pack.id} ${pack.name}` : id;
}

/** The Trace link for an answer: an explicit href wins, then a run ID, else none. */
export function traceHref(trace?: { href?: string | null; runId?: string | null } | null): string | null {
  if (!trace) return null;
  if (trace.href && trace.href.startsWith("/")) return trace.href;
  if (trace.runId && trace.runId.trim()) return `/trace/${encodeURIComponent(trace.runId.trim())}`;
  return null;
}

/** Confidence from a 0..1 score, for engines that return a number rather than a level. */
export function confidenceFromScore(score: number | null | undefined): Confidence {
  if (score == null || Number.isNaN(score)) return "medium";
  if (score >= 0.8) return "high";
  if (score >= 0.5) return "medium";
  return "low";
}

/** The plain-text form of a Powered-by strip, for exports and AI answers. */
export function poweredByText(p: { pack: string; rule?: string | null; article?: string | null; confidence?: Confidence | null }): string {
  const parts = [`Powered by ${packTitle(p.pack)}`];
  const rule = p.rule ? findRule(p.rule) : undefined;
  if (p.rule) parts.push(p.rule.toUpperCase());
  const article = p.article ?? rule?.rule.source;
  if (article) parts.push(article);
  if (p.confidence) parts.push(CONFIDENCE_LABEL[p.confidence]);
  return parts.join(" · ");
}
