/**
 * The one number formatter (PLAN_R5 G5). Every number on every screen, table, chart tooltip and AI answer goes
 * through here; `backend/common/format.py` is its Python twin for Word/Excel exports and AI commentary.
 *
 *   amounts      SAR m or bn, 1–2 decimals      fmt.sar(1234.5) -> "SAR 1.23bn", fmt.sar(12.34) -> "SAR 12.3m"
 *   percentages  1–2 decimals                   fmt.pct(0.1218) -> "12.18%" (fraction), fmt.pct(12.18, {scale: "points"})
 *   ratios       2 decimals                     fmt.ratio(1.23456) -> "1.23"
 *   bps          integer                        fmt.bps(43.6) -> "44 bps"
 *   counts       thousands separators           fmt.count(12345) -> "12,345"
 *
 * `fmt.auto(value, key)` picks the right one from a column key or unit, and `fmt.header(key)` turns a key into a
 * plain-words header with its unit ("headroom_share" -> "Headroom share (%)"). Contract: docs/v5/THREAD_API.md 3.
 */

export type Num = number | null | undefined;
const DASH = "–";

function ok(v: Num): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

function fixed(v: number, dp: number): string {
  return v.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

/** An amount given in SAR millions. >= 1,000m shows in bn with 2 decimals; otherwise m with 1 (2 below 10m). */
export function sar(millions: Num, unit?: "m" | "bn"): string {
  if (!ok(millions)) return DASH;
  const abs = Math.abs(millions);
  if (millions === 0) return "SAR 0m";
  const bn = unit ? unit === "bn" : abs >= 1000;
  if (bn) return `SAR ${fixed(millions / 1000, 2)}bn`;
  return `SAR ${fixed(millions, abs < 10 ? 2 : 1)}m`;
}

export interface PctOpts { scale?: "fraction" | "points"; dp?: number; signed?: boolean }

/** A percentage. Default input is a fraction (0.1218 -> 12.18%); `scale: "points"` when the value is already in %. */
export function pct(v: Num, opts: PctOpts = {}): string {
  if (!ok(v)) return DASH;
  const points = opts.scale === "points" ? v : v * 100;
  const dp = opts.dp ?? (Math.abs(points) >= 10 ? 1 : 2);
  const s = fixed(points, Math.min(2, Math.max(1, dp)));
  return `${opts.signed && points > 0 ? "+" : ""}${s}%`;
}

export function ratio(v: Num): string {
  return ok(v) ? fixed(v, 2) : DASH;
}

export function bps(v: Num, opts: { signed?: boolean } = {}): string {
  if (!ok(v)) return DASH;
  const n = Math.round(v) || 0; // never "-0 bps"
  return `${opts.signed && n > 0 ? "+" : ""}${n.toLocaleString("en-US")} bps`;
}

/** Percentage points: "+2.53pp". */
export function pp(v: Num, opts: { signed?: boolean } = {}): string {
  if (!ok(v)) return DASH;
  const d = Math.abs(v) >= 10 ? 1 : 2;
  const x = Number(v.toFixed(d)) || 0;
  return `${opts.signed && x > 0 ? "+" : ""}${fixed(x, d)}pp`;
}

export function count(v: Num): string {
  return ok(v) ? Math.round(v).toLocaleString("en-US") : DASH;
}

/** A plain number that is none of the above: thousands separators, at most 2 decimals. */
export function num(v: Num): string {
  if (!ok(v)) return DASH;
  if (Number.isInteger(v)) return v.toLocaleString("en-US");
  return fixed(v, Math.abs(v) >= 100 ? 1 : 2);
}

export type Kind = "sar" | "sar_bn" | "pct_fraction" | "pct_points" | "pct_auto" | "pp" | "ratio" | "bps" | "count" | "num";

/** A yes/no column ("clears_hurdle", "is_watchlist", "has_breach"): never a percentage or an amount. */
const FLAG = /^(clears|is|has|passes|meets|breached|flag)(_|$)|_flag$|^(feasible|pass|ok)$/;

/** A raw float as text ("0.2810632681763545"): what G5 never lets through. */
export const RAW_FLOAT = /^-?\d+\.\d{5,}$/;

/** What kind of number a column key or unit holds. */
export function kindOf(keyOrUnit: string): Kind {
  const k = keyOrUnit.toLowerCase().replace(/[\s-]+/g, "_");
  if (FLAG.test(k)) return "num";
  if (/(_type|_name|_code|_band|_label|_kind|_status|_date|_period|_grade|_rating)$/.test(k)) return "num";
  if (/(^|_)bps$|_bp$|basis_points/.test(k)) return "bps";
  if (/(_pp$|_pp_|^pp$|percentage_points)/.test(k)) return "pp";
  if (/(_pct|percent|_%|^%$|^pct$|_pct_)/.test(k)) return "pct_points";
  if (/(_sar_bn|_bn$|^sar_bn$)/.test(k)) return "sar_bn";
  if (/(count|^n$|^n_|_n$|number_of|borrowers$|facilities$|accounts$|customers$|names$|obligors$|warned$|_ids?$|rows$)/.test(k)) return "count";
  if (/(dscr|leverage|multiple|gini|auc|(^|_)ks($|_)|psi|(^|_)iv($|_)|vif|woe|^ratio$|_ratio$|hhi|brier|z_score|beta)/.test(k)) return "ratio";
  if (/(share|rate|coverage|utili[sz]ation|ltv|weight|probability|(^|_)pd($|_)|(^|_)lgd($|_)|ccf|raroc|roe|hurdle|margin|yield|growth|change_rel|concentration|cost_of_risk)/.test(k)) return "pct_auto";
  if (/(sar|(^|_)ead($|_)|(^|_)ecl($|_)|limit|exposure|amount|rwa|capital|headroom|balance|income|(^|_)sva($|_)|_mn$|_m$|outstanding|provision|collateral_value|loss|profit|fee)/.test(k)) return "sar";
  return "num";
}

/** Format a value by its column key or unit (see kindOf). Strings pass through. */
export function auto(v: unknown, keyOrUnit = ""): string {
  if (v === null || v === undefined) return DASH;
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "string" && RAW_FLOAT.test(v.trim())) return auto(Number(v.trim()), keyOrUnit);
  if (typeof v !== "number") return String(v);
  if (!Number.isFinite(v)) return DASH;
  switch (kindOf(keyOrUnit)) {
    case "sar": return sar(v);
    case "sar_bn": return sar(v * 1000);
    case "pct_points": return pct(v, { scale: "points" });
    case "pct_fraction": return pct(v);
    case "pct_auto": return pct(v, { scale: Math.abs(v) <= 1.5 ? "fraction" : "points" });
    case "pp": return pp(v);
    case "ratio": return ratio(v);
    case "bps": return bps(v);
    case "count": return count(v);
    default: return num(v);
  }
}

/** The kind a header in words implies by its unit: "Lifetime RAROC (%)" -> pct_auto, "SVA (SAR m)" -> sar. */
function kindOfLabel(label: string): Kind | null {
  const l = label.toLowerCase();
  if (/\(%\)|\(% of/.test(l)) return "pct_auto";
  if (/\(sar ?bn\)/.test(l)) return "sar_bn";
  if (/\(sar ?mn?\)|\(sar\)/.test(l)) return "sar";
  if (/\(bps\)/.test(l)) return "bps";
  if (/\(pp\)/.test(l)) return "pp";
  if (/\(x\)/.test(l)) return "ratio";
  return null;
}

const KIND_KEY: Record<Kind, string> = {
  sar: "amount", sar_bn: "sar_bn", pct_fraction: "share", pct_points: "pct", pct_auto: "share", pp: "pp", ratio: "ratio",
  bps: "bps", count: "count", num: "",
};

/**
 * One table cell, from its value and whatever describes its column (a key, a header in words with its unit, or
 * both). Every generic table renderer routes its cells through here (PLAN_R6 E2): booleans read Yes/No, numbers
 * follow the column's kind, raw floats sent as text are parsed first, other text passes through unchanged.
 * Safety net: a number whose column says nothing about it still never shows more than 2 decimals.
 */
export function cell(v: unknown, key = "", label = ""): string {
  if (v === null || v === undefined || v === "") return DASH;
  if (typeof v === "boolean") return v ? "Yes" : "No";
  let n: number | null = null;
  if (typeof v === "number") n = v;
  else if (typeof v === "string" && RAW_FLOAT.test(v.trim())) n = Number(v.trim());
  if (n === null) return String(v);
  if (!Number.isFinite(n)) return DASH;
  const byLabel = label ? kindOfLabel(label) : null;
  if (byLabel) return auto(n, KIND_KEY[byLabel]);
  return auto(n, key || label.replace(/\(.*?\)/g, "").trim());
}

/** The Plotly d3 format of a value of this kind, with its unit around it: "SAR %{y:,.1f}m", "%{y:.1%}". */
export function hoverValue(keyOrUnit: string, axis = "y"): string {
  switch (kindOf(keyOrUnit)) {
    case "sar": return `SAR %{${axis}:,.1f}m`;
    case "sar_bn": return `SAR %{${axis}:,.2f}bn`;
    case "pct_auto": case "pct_fraction": return `%{${axis}:.1%}`;
    case "pct_points": return `%{${axis}:.1f}%`;
    case "pp": return `%{${axis}:.2f}pp`;
    case "bps": return `%{${axis}:,.0f} bps`;
    case "count": return `%{${axis}:,.0f}`;
    default: return `%{${axis}:,.2f}`;
  }
}

/** A whole hovertemplate for one series (PLAN_R6 E2): "<category><br><value with unit>", never a raw float. */
export function hoverTemplate(keyOrUnit: string, valueAxis = "y", categoryAxis = "x", name = ""): string {
  return `%{${categoryAxis}}<br>${name ? `${name}: ` : ""}${hoverValue(keyOrUnit, valueAxis)}<extra></extra>`;
}

const ACRONYMS: Record<string, string> = {
  ead: "EAD", ecl: "ECL", pd: "PD", lgd: "LGD", rwa: "RWA", raroc: "RAROC", sva: "SVA", ltv: "LTV", dscr: "DSCR", hhi: "HHI",
  npl: "NPL", dpd: "DPD", ccf: "CCF", ftp: "FTP", rm: "RM", id: "ID", psi: "PSI", csi: "CSI", iv: "IV", ks: "KS", auc: "AUC",
  mev: "MEV", ews: "EWS", sicr: "SICR", sar: "SAR", roe: "ROE", gdp: "GDP", vif: "VIF", woe: "WoE", el: "EL", cor: "CoR",
  q1: "Q1", q2: "Q2", q3: "Q3", q4: "Q4", sme: "SME", xgb: "XGBoost", yoy: "YoY", qoq: "QoQ",
};
const UNIT_TOKENS = new Set(["sar", "mn", "m", "bn", "pct", "pp", "bps", "bp"]);

/** A column key in plain words with its unit: "headroom_sar_mn" -> "Headroom (SAR m)", "share_of_book" -> "Share of book (%)". */
export function header(key: string): string {
  if (!key) return "";
  if (/[A-Z ]/.test(key) && !/_/.test(key) && key !== key.toUpperCase()) return key; // already words
  const kind = kindOf(key);
  if (FLAG.test(key.toLowerCase())) return key.charAt(0).toUpperCase() + key.slice(1).toLowerCase().replace(/_/g, " ");
  const words = key.toLowerCase().split(/[_\s]+/).filter(Boolean).filter((w, i, all) => !(UNIT_TOKENS.has(w) && all.length > 1));
  const text = words.map((w, i) => ACRONYMS[w] ?? (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w)).join(" ");
  const unit = kind === "sar" ? " (SAR m)" : kind === "sar_bn" ? " (SAR bn)" : kind === "pct_points" || kind === "pct_auto" || kind === "pct_fraction" ? " (%)" : kind === "bps" ? " (bps)" : kind === "pp" ? " (pp)" : "";
  return text + unit;
}

/** Long decimals in prose are rounded to 2 places (G5: nothing with more than 4 decimals ever shows). */
export function tidyText(text: string): string {
  return String(text ?? "").replace(/(^|[^\d.\w])(-?\d+)\.(\d{3,})(?![\d.])/g, (_m, pre: string, int: string, dec: string) =>
    `${pre}${Number(`${int}.${dec}`).toFixed(2)}`);
}

export const fmt = { sar, pct, pp, ratio, bps, count, num, auto, cell, hoverValue, hoverTemplate, header, kindOf, tidyText };
export default fmt;
