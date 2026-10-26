/** R14 r: house formats for the issue view (pure: tested with node --test). */

/** A table cell in house format (the API sends raw numbers with a unit per column). */
export function cell(v: unknown, unit: string): string {
  if (v === null || v === undefined || v === "") return "–";
  if (unit === "text" || typeof v === "string") return String(v);
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  if (unit === "SAR mn") {
    const a = Math.abs(n);
    const sign = n < -0.005 ? "−" : "";
    if (a >= 1000) return `${sign}SAR ${(a / 1000).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}bn`;
    return `${sign}SAR ${a.toLocaleString("en-US", { minimumFractionDigits: a < 10 ? 2 : 1, maximumFractionDigits: a < 10 ? 2 : 1 })}m`;
  }
  if (unit === "%") return `${n.toFixed(1)}%`;
  if (unit === "n") return Math.round(n).toLocaleString("en-US");
  return Number.isInteger(n) ? n.toLocaleString("en-US") : n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

/** "2026-11-09" -> "9 Nov 2026". */
export function dueText(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
