/**
 * Round D (PLAN_DEALDESK_EDITION row D): the Deposit requirement term in words, for the term sheet, the ask and the lever
 * reads. The backend is backend/dealdesk/deposit_requirement (the term, the engine's channels and the documents); no figure is
 * computed here: the cell prints the term's own inputs, and the engine's amount when the analysis carries it.
 */

export type DepositType = "none" | "lien_cash" | "relationship";

/** The term's keys on a term set (absent = neutral). */
export interface DepositTerms {
  deposit_type?: DepositType | string; deposit_pct?: number; deposit_amount?: number; deposit_tenor_months?: number; deposit_facility?: string;
  currency?: string;
}

/** What the engine used and did (`analysis.deposit`). */
export interface DepositEffect {
  type: DepositType; label: string; pct: number; amount: number; basis: "pct" | "amount"; tenor_months: number; facility: string;
  amount_sar_mn: number; channel: string; formula: string; maintenance: string;
  ead_y1?: number; ead_net_y1?: number; recognised_y1_sar_mn?: number; haircut?: number;
  funding_value_pa_sar_mn?: number; pv_funding_value_sar_mn?: number; relationship_raroc_uplift?: number | null;
  parameters?: Record<string, string>; note?: string;
}

export const DEPOSIT_NEUTRAL: Required<Omit<DepositTerms, "currency">> = {
  deposit_type: "none", deposit_pct: 0, deposit_amount: 0, deposit_tenor_months: 0, deposit_facility: "",
};

export const DEPOSIT_TYPE: Record<string, string> = {
  none: "None", lien_cash: "Lien-marked cash collateral", relationship: "Operating balances (relationship)",
};

/** True when the terms carry a deposit requirement. */
export function hasDeposit(t: DepositTerms | null | undefined): boolean {
  if (!t) return false;
  const typ = t.deposit_type ?? "none";  // a size with no type is lien-marked cash (the "require a deposit" lever's default)
  return (typ === "lien_cash" || typ === "relationship" || typ === "none") && ((t.deposit_pct ?? 0) > 0 || (t.deposit_amount ?? 0) > 0);
}

const n1 = (v: number) => v.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const n0 = (v: number) => v.toLocaleString("en-US", { maximumFractionDigits: 1 });

/** The term sheet cell: "Lien-marked cash · 30% of limit · life of facility" (+ the engine's amount when given, SAR m). */
export function depositRead(t: DepositTerms | null | undefined, engineAmount?: number | null): string {
  if (!t || !hasDeposit(t)) return "None";
  const ccy = t.currency ?? "SAR";
  const kind = t.deposit_type === "relationship" ? "Operating balances" : "Lien-marked cash";
  let amt = (t.deposit_amount ?? 0) > 0 ? `${ccy} ${n1(t.deposit_amount ?? 0)}m` : `${n0(t.deposit_pct ?? 0)}% of limit`;
  if ((t.deposit_amount ?? 0) <= 0 && typeof engineAmount === "number") amt += ` (${ccy} ${n1(engineAmount)}m)`;
  const per = (t.deposit_tenor_months ?? 0) > 0 ? `${t.deposit_tenor_months} months` : "life of facility";
  const fac = t.deposit_facility && !["proposed", "this"].includes(t.deposit_facility)
    ? ` · secures ${t.deposit_facility === "all" ? "all facilities" : t.deposit_facility}` : "";
  return `${kind} · ${amt} · ${per}${fac}`;
}

/** The engine's effect in one line, for a tooltip or an info line. */
export function depositEffectRead(e: DepositEffect | null | undefined): string {
  if (!e) return "";
  return e.formula;
}
