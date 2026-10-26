/** Words and number formats of Scorecard Validation: pure, so they are unit-tested without the browser. */

export type Status = "green" | "amber" | "red" | "na";
export type Conclusion = "fit" | "conditions" | "not_fit";

export const STATUS_WORD: Record<Status, string> = { green: "Green", amber: "Amber", red: "Red", na: "Not applicable" };
export const CONCLUSION_WORD: Record<Conclusion, string> = { fit: "Fit for use", conditions: "Fit for use with conditions", not_fit: "Not fit for use" };
export const SUGGESTED: Record<Status, Conclusion> = { green: "fit", amber: "conditions", red: "not_fit", na: "fit" };

export function fmt(value: unknown, format: string): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return format === "rag" ? STATUS_WORD[value as Status] ?? value : value;
  const v = Number(value);
  if (!Number.isFinite(v)) return "—";
  switch (format) {
    case "pct": return `${(v * 100).toFixed(1)}%`;
    case "pct2": return `${(v * 100).toFixed(2)}%`;
    case "num4": return v.toFixed(4);
    case "int": return Math.round(v).toLocaleString("en-US");
    default: return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
}

export function when(t: number): string {
  return t ? new Date(t * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "—";
}
