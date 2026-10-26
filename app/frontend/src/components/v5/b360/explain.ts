/**
 * R6 E4: the (i) explanations for every Borrower 360 history chart. The text per tab
 * says what the chart shows, how each series is calculated and what to look for; the
 * example is read off the drawn figure itself (the latest period of each series).
 */

import { type ChartExplain, exNum } from "../core/chart-explain-core.ts";

type Trace = { name?: unknown; x?: unknown; y?: unknown; customdata?: unknown };

/** Series drawn as a rank whose real value (a grade or band) is in customdata. */
const LABELLED = new Set(["Rating", "At origination", "Band"]);

/** How each series is calculated, by its name in the figure (a trailing id is ignored: "EAD F-001" -> "EAD"). */
export const SERIES: Record<string, string> = {
  "EAD": "**EAD by exposure** = exposure at default of each facility (SAR m), stacked so the bar's height is the borrower's total.",
  "ECL (total)": "**ECL (total)** = sum of expected credit loss across the facilities = PD × LGD × EAD, per facility.",
  "Rating": "**Rating** = the internal grade each quarter, placed on the global scale (AAA at the top).",
  "At origination": "**At origination** = the grade when the facility was granted, as a dotted reference.",
  "PD (TTC 12m, %)": "**PD** = the through-the-cycle 12-month probability of default of the grade, × 100.",
  "Behaviour score": "**Behaviour score** = the monthly retail behaviour score from repayment and account conduct (higher is better).",
  "Band": "**Band** = the score band, A best to E worst (drawn as its rank).",
  "DPD": "**DPD by exposure** = days past due of each facility at the period end.",
  "Worst stage": "**Worst stage** = the highest IFRS 9 stage across the facilities (1 performing, 2 increased risk, 3 impaired).",
  "Collateral value": "**Collateral value** = the latest valuation of the pledged collateral (SAR m).",
  "Collateral over EAD (%)": "**Cover** = collateral value ÷ EAD × 100.",
  "Breaches": "**Breaches** = count of covenants tested and failed in the quarter.",
  "On watch": "**On watch** = count of covenants within the watch margin of their threshold.",
  "Lowest headroom (%)": "**Lowest headroom** = the smallest (actual − threshold) ÷ threshold × 100 across covenants.",
  "Revenue": "**Revenue** = reported quarterly revenue (SAR m).",
  "EBITDA": "**EBITDA** = earnings before interest, tax, depreciation and amortisation (SAR m).",
  "Leverage (x)": "**Leverage** = total debt ÷ EBITDA (annualised), in times.",
  "DSCR (x)": "**DSCR** = cash available for debt service ÷ debt service due, in times (below 1 means it cannot cover its payments).",
  "Inflows": "**Inflows** = total credits into the customer's accounts in the month (SAR thousand).",
  "3-month average": "**3-month average** = mean of the last three months' inflows.",
  "Balance buffer (months)": "**Balance buffer** = average balance ÷ average monthly outflows, in months of spending covered.",
  "Salary missing": "**Salary missing** = 1 when the expected salary credit did not arrive that month.",
  "Borrowers": "**Borrowers** = count of group members with that rating.",
  "Warned (EWS moderate or worse)": "**Warned** = count of those members with an Early Warning band of moderate or worse.",
  "Score": "**Score** = sum of the weights of the Early Warning rules that fired in the period (higher is worse).",
  "Bank internal": "**Bank internal / Bureau / Open Banking** = count of rules fired from each data source.",
  "Bureau": "**Bureau** = count of rules fired from credit bureau data.",
  "Open Banking": "**Open Banking** = count of rules fired from open-banking account data.",
  "External exposure": "**External exposure** = the borrower's borrowing at other lenders, from the bureau (SAR m).",
  "External DPD": "**External DPD** = worst days past due reported by other lenders.",
  "Bureau score": "**Bureau score** = the credit bureau's score for the customer (higher is better).",
  "Operating inflows": "**Operating inflows** = credits from operations into the borrower's accounts in the quarter (SAR m).",
  "Inflow trend (%)": "**Inflow trend** = change in operating inflows on the same quarter a year earlier, × 100.",
};

/** What to look for, by tab. */
export const LOOK: Record<string, string> = {
  "exposure": "ECL rising **faster than EAD**: the risk per riyal lent is going up, not just the amount lent.",
  "ratings": "A **step down** below the origination grade, or a score sliding across band boundaries: credit quality has worsened since approval.",
  "stage-dpd": "DPD climbing towards **30 days** (the usual Stage 2 trigger) and **90 days** (default).",
  "collateral": "Cover **falling below 100%**: the collateral no longer covers the exposure if the borrower defaults.",
  "covenants": "Headroom **shrinking towards zero** before any breach shows: the warning comes early.",
  "financials": "Leverage rising while **DSCR falls towards 1x**: debt is growing faster than the cash to pay it.",
  "group": "Warned members in **good grades**: stress in the group that the ratings have not caught yet.",
  "ews": "The score **rising across periods** and rules firing from more than one source: independent signals agreeing.",
  "bureau": "**External arrears** or exposure growing at other lenders while ours looks clean: trouble shows there first.",
  "open-banking": "Inflows **falling for several periods** or the buffer running down: less cash coming in to repay.",
};

export const SHOWS: Record<string, string> = {
  "exposure": "The borrower's exposure by facility and its total expected credit loss, period by period.",
  "ratings": "How the borrower's credit grade or behaviour score has moved over time.",
  "stage-dpd": "How late each facility is with its payments, and the worst IFRS 9 stage.",
  "collateral": "What the collateral is worth and how much of the exposure it covers.",
  "covenants": "Covenant test results: breaches, near-misses and the tightest headroom.",
  "financials": "The borrower's financial performance and its debt-carrying capacity.",
  "group": "The other members of the borrower's group by rating, and how many are warned.",
  "ews": "The Early Warning score over time and which data sources the fired rules came from.",
  "bureau": "What other lenders report about this borrower.",
  "open-banking": "Cash flowing through the borrower's accounts.",
};

const baseName = (name: string) => (SERIES[name] ? name : name.replace(/\s+\S+$/, ""));

function fmtValue(y: number): string {
  return exNum(y, Number.isInteger(y) ? 0 : Math.abs(y) < 10 ? 2 : 1);
}

/** The latest drawn value of a trace, as text (a grade or band where the trace is drawn as a rank). */
function lastValue(t: Trace): { x: string; text: string } | null {
  const xs = Array.isArray(t.x) ? t.x : [];
  const ys = Array.isArray(t.y) ? t.y : [];
  const cd = Array.isArray(t.customdata) ? t.customdata : [];
  for (let i = ys.length - 1; i >= 0; i--) {
    const v = ys[i];
    if (v == null || v === "" || !Number.isFinite(Number(v))) continue;
    const label = LABELLED.has(String(t.name ?? "")) && typeof cd[i] === "string" && cd[i] ? String(cd[i]) : null;
    return { x: String(xs[i] ?? ""), text: label ?? fmtValue(Number(v)) };
  }
  return null;
}

/** The explanation of a Borrower 360 tab chart, from its tab key, label and drawn traces. */
export function tabChartExplain(tabKey: string, label: string, traces: Trace[]): ChartExplain {
  const names = traces.map((t) => String(t.name ?? "")).filter(Boolean);
  const seen = new Set<string>();
  const formula: string[] = [];
  for (const nm of names) {
    const b = baseName(nm);
    const f = SERIES[b] ?? `**${nm}** = the value the Borrower 360 service publishes for the period.`;
    if (!seen.has(f)) { seen.add(f); formula.push(f); }
  }
  if (!formula.length) formula.push("**Each series** = the value the Borrower 360 service publishes for the period.");
  const pts = traces.map((t) => ({ name: String(t.name ?? ""), v: lastValue(t) })).filter((p) => p.v).slice(0, 3);
  const at = pts[0]?.v?.x;
  const lead = !at ? "" : tabKey === "group" ? `In grade ${at}: ` : `At ${at}: `;
  const read = pts.length
    ? `${lead}${pts.map((p) => `${p.name} **${p.v!.text}**`).join(", ")}. Hover any point for its exact value.`
    : "Each point is one period, oldest on the left; hover a point for its exact value.";
  return {
    shows: `${SHOWS[tabKey] ?? label} ${label ? `(${label.charAt(0).toLowerCase()}${label.slice(1)}).` : ""}`.trim(),
    formula,
    read,
    lookFor: LOOK[tabKey] ?? "A **sustained move in one direction** over several periods rather than a single spike.",
  };
}
