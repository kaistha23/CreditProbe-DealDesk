/**
 * R14 G (K34): small number formats for the plain-words writers. Pure (node-testable), no "@/" imports.
 * Every writer names at least one number from its panel's own result; these keep the formats one way everywhere.
 */

export type Num = number | null | undefined;

/** A figure that may arrive as {value} (sourced) or as a bare number. */
export function v(x: unknown): number | null {
  if (typeof x === "number" && Number.isFinite(x)) return x;
  if (x && typeof x === "object" && "value" in (x as Record<string, unknown>)) {
    const y = (x as { value: unknown }).value;
    return typeof y === "number" && Number.isFinite(y) ? y : null;
  }
  return null;
}

/** SAR millions: "SAR 1,234m", "SAR 12.5m", "SAR 1.2bn". */
export function sar(m: Num, dp?: number): string {
  if (m == null || !Number.isFinite(m)) return "n/a";
  const a = Math.abs(m);
  if (a >= 1000) return `SAR ${(m / 1000).toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 })}bn`;
  const d = dp ?? (a >= 100 ? 0 : 1);
  return `SAR ${m.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d })}m`;
}

/** Signed SAR millions: "+SAR 3.2m", "−SAR 0.4m". */
export function dsar(m: Num, dp?: number): string {
  if (m == null || !Number.isFinite(m)) return "n/a";
  return `${m < 0 ? "−" : "+"}${sar(Math.abs(m), dp)}`;
}

/** A share 0–1 as a percent: 0.453 → "45%" (dp 0) or "45.3%". */
export function pct(share: Num, dp = 0): string {
  if (share == null || !Number.isFinite(share)) return "n/a";
  return `${(share * 100).toFixed(dp)}%`;
}

/** A value already in percent: 14.5 → "14.5%". */
export function pctv(p: Num, dp = 1): string {
  if (p == null || !Number.isFinite(p)) return "n/a";
  return `${p.toFixed(dp)}%`;
}

/** A ratio: 1.6 → "1.60x". */
export function x(r: Num, dp = 2): string {
  if (r == null || !Number.isFinite(r)) return "n/a";
  return `${r.toFixed(dp)}x`;
}

/** An integer count with separators: 2501 → "2,501". */
export function n(k: Num): string {
  if (k == null || !Number.isFinite(k)) return "n/a";
  return Math.round(k).toLocaleString("en-US");
}

/** "1 name" / "3 names". */
export function plural(k: number, one: string, many = `${one}s`): string {
  return `${n(k)} ${k === 1 ? one : many}`;
}

/** Trim a writer's sentence: no double spaces, ends with a full stop. */
export function sentence(s: string): string {
  const t = s.replace(/\s+/g, " ").trim();
  return /[.!?:]$/.test(t) ? t : `${t}.`;
}

/** Keep 3–4 non-empty lines (the block's rule), each a sentence. */
export function lines(...xs: (string | null | undefined | false)[]): string[] {
  return xs.filter((s): s is string => typeof s === "string" && s.trim().length > 0).map(sentence).slice(0, 4);
}
