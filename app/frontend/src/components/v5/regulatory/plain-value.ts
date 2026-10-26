/**
 * R14 r (R13 X gap 1): a backend value (parameters, expected results, bound parameters) in plain words instead of
 * raw JSON: `{"min_dpd": 90, "books": ["corporate"]}` -> "min dpd: 90; books: corporate".
 */
export function humanKey(k: string): string {
  return k.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
}

export function plainValue(v: unknown, depth = 0): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString("en-US") : v.toLocaleString("en-US", { maximumFractionDigits: 6 });
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return v.length ? v.map((x) => plainValue(x, depth + 1)).join(", ") : "none";
  if (typeof v === "object") {
    const entries = Object.entries(v as Record<string, unknown>);
    if (!entries.length) return "none";
    const inner = entries.map(([k, x]) => `${humanKey(k)}: ${plainValue(x, depth + 1)}`).join("; ");
    return depth > 0 ? `(${inner})` : inner;
  }
  return String(v);
}

/**
 * R14 r (R13 X gap 1): the shell's "not in this runtime" error names an API path; on screen it reads as debug text.
 * Say it in words instead, without the path.
 */
export function runtimeMessage(message: string | null | undefined, what = "This part of CreditProbe"): string {
  const m = String(message ?? "");
  if (/served by the main CreditProbe backend|not part of this isolated|not_in_this_runtime/i.test(m)) {
    return `${what} runs on the full CreditProbe platform, which is not switched on in this installation.`;
  }
  return m;
}
