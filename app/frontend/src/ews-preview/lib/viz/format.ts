/**
 * Concise, adaptive, semantically correct display of governed numbers.
 *
 * PRESENTATION ONLY. The raw value is never changed, never rounded in place
 * and always kept for hover, tooltips and export: every function here takes
 * the raw number and returns a string. The master specification's §9 rules:
 *
 * * Narrative amounts use compact finance notation: SAR 171m, SAR 2.60m,
 *   SAR 23.3bn -- never "SAR million" after every figure.
 * * A table puts the unit ONCE in the header ("EAD (SAR m)") and the cells
 *   carry plain numbers at ONE scale chosen for the whole column.
 * * A chart's axis title carries the unit once; hover shows the compact
 *   value and the precise raw value.
 * * PD / LGD / CCF are percentages ("2.00%"), never "0.02x". A multiplier is
 *   written ×1.20 and is reserved for scenario multipliers.
 * * Small Retail amounts must not round to zero: precision grows until two
 *   significant digits of the smallest non-zero value are visible.
 *
 * Every published book in V4 stores money in SAR MILLION (manifest
 * `amount_scale`), so inputs here are in millions unless a function says
 * otherwise.
 */

export type Scale = "SAR" | "SAR k" | "SAR m" | "SAR bn";

const SCALE_FACTOR: Record<Scale, number> = {
  SAR: 1e-6,
  "SAR k": 1e-3,
  "SAR m": 1,
  "SAR bn": 1e3,
};

/** The scale a set of values (in SAR million) should share. */
export function scaleFor(valuesInMillions: number[]): Scale {
  const finite = valuesInMillions.filter((v) => Number.isFinite(v) && v !== 0);
  if (!finite.length) return "SAR m";
  const peak = Math.max(...finite.map((v) => Math.abs(v)));
  if (peak >= 1000) return "SAR bn";
  if (peak >= 1) return "SAR m";
  if (peak >= 0.001) return "SAR k";
  return "SAR";
}

/** Convert a value in SAR million into the given scale. */
export function toScale(valueInMillions: number, scale: Scale): number {
  return valueInMillions / SCALE_FACTOR[scale];
}

/**
 * Decimals so the SMALLEST non-zero magnitude shows two significant digits,
 * capped at 4; at or above 100 no decimals, at or above 10 one.
 */
export function decimalsFor(scaledValues: number[]): number {
  const finite = scaledValues.filter((v) => Number.isFinite(v) && v !== 0).map(Math.abs);
  if (!finite.length) return 0;
  // ONE precision per group (the governed U01 rule): chosen from the
  // SMALLEST non-zero magnitude so it keeps two significant digits.
  const smallest = Math.min(...finite);
  if (smallest >= 100) return 0;
  if (smallest >= 10) return 1;
  if (smallest >= 1) return 2;
  return Math.min(Math.ceil(-Math.log10(smallest)) + 1, 4);
}

/** The scale a TABLE column shares: chosen from its median magnitude. */
export function columnScaleFor(valuesInMillions: number[]): Scale {
  const finite = valuesInMillions.filter((v) => Number.isFinite(v) && v !== 0).map(Math.abs);
  if (!finite.length) return "SAR m";
  const sorted = [...finite].sort((a, b) => a - b);
  return scaleFor([sorted[Math.floor(sorted.length / 2)]]);
}

function grouped(value: number, decimals: number): string {
  // Round half away from zero on the DECIMAL value the reader expects:
  // 23.275 is stored as 23.27499999…, and `toFixed` alone would show 23.27.
  const factor = 10 ** decimals;
  const rounded = Math.round(Number((Math.abs(value) * factor).toPrecision(12))) / factor;
  const fixed = rounded.toFixed(decimals);
  const [whole, frac] = fixed.split(".");
  const withSep = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const sign = value < 0 && Number(fixed) !== 0 ? "−" : "";
  return `${sign}${withSep}${frac ? `.${frac}` : ""}`;
}

const SUFFIX: Record<Scale, string> = { SAR: "", "SAR k": "k", "SAR m": "m", "SAR bn": "bn" };

/** "SAR 171m", "SAR 2.60m", "SAR 23.3bn", "SAR 845k". Input in SAR million. */
export function sar(valueInMillions: number | null | undefined): string {
  if (valueInMillions === null || valueInMillions === undefined || !Number.isFinite(valueInMillions)) {
    return "—";
  }
  if (valueInMillions === 0) return "SAR 0";
  const scale = scaleFor([valueInMillions]);
  const scaled = toScale(valueInMillions, scale);
  const abs = Math.abs(scaled);
  const decimals = abs >= 100 ? 0 : abs >= 10 ? 1 : 2;
  return `SAR ${grouped(scaled, decimals)}${SUFFIX[scale]}`;
}

/** A signed movement: "+SAR 31m", "−SAR 0.34m". */
export function sarDelta(valueInMillions: number | null | undefined): string {
  if (valueInMillions === null || valueInMillions === undefined || !Number.isFinite(valueInMillions)) {
    return "—";
  }
  const text = sar(Math.abs(valueInMillions));
  if (valueInMillions > 0) return `+${text}`;
  if (valueInMillions < 0) return `−${text}`;
  return text;
}

/** A column of money at ONE scale: header suffix + cell strings. */
export function moneyColumn(valuesInMillions: (number | null)[]): {
  scale: Scale;
  header: string;
  cells: string[];
} {
  const finite = valuesInMillions.filter((v): v is number => v !== null && Number.isFinite(v));
  const scale = columnScaleFor(finite);
  const scaled = finite.map((v) => toScale(v, scale));
  const decimals = decimalsFor(scaled);
  return {
    scale,
    header: `(${scale})`,
    cells: valuesInMillions.map((v) =>
      v === null || !Number.isFinite(v) ? "—" : grouped(toScale(v, scale), decimals),
    ),
  };
}

/** A rate held as a FRACTION (0.02) displayed as a percentage ("2.00%"). */
export function pct(fraction: number | null | undefined, decimals = 2): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return "—";
  return `${grouped(fraction * 100, decimals)}%`;
}

/** A value already in percent units (12.5 -> "12.50%"). */
export function pctPoints(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${grouped(value, decimals)}%`;
}

/** A signed percentage change: "+18.2%". */
export function pctChange(fraction: number | null | undefined, decimals = 1): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return "—";
  const text = grouped(Math.abs(fraction) * 100, decimals);
  return `${fraction > 0 ? "+" : fraction < 0 ? "−" : ""}${text}%`;
}

/** Basis points: "+14 bps". Input is a fraction difference (0.0014). */
export function bps(fractionDelta: number | null | undefined): string {
  if (fractionDelta === null || fractionDelta === undefined || !Number.isFinite(fractionDelta)) return "—";
  const v = fractionDelta * 10000;
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${grouped(Math.abs(v), Math.abs(v) < 10 ? 1 : 0)} bps`;
}

/** A scenario multiplier, and ONLY a scenario multiplier: "×1.20". */
export function multiplier(factor: number | null | undefined): string {
  if (factor === null || factor === undefined || !Number.isFinite(factor)) return "—";
  return `×${factor.toFixed(2)}`;
}

/**
 * A times-covered ratio: "1.35x". NOT a percentage and NOT a scenario
 * multiplier -- DSCR, interest coverage and leverage are counts of times, so
 * a 1.35 DSCR is "1.35x" and never "1.35%" or "135.00 pp".
 */
export function ratio(times: number | null | undefined, decimals = 2): string {
  if (times === null || times === undefined || !Number.isFinite(times)) return "—";
  return `${times.toFixed(decimals)}x`;
}

/** A plain count: "14,203". */
export function count(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return grouped(Math.round(value), 0);
}

/** A precise raw value for hover and export: never scaled, never rounded away. */
export function raw(valueInMillions: number | null | undefined): string {
  if (valueInMillions === null || valueInMillions === undefined || !Number.isFinite(valueInMillions)) {
    return "—";
  }
  return `${valueInMillions} SAR million (raw)`;
}

/** Format a value by its governed unit. */
export function byUnit(value: number | null | undefined, unit: string): string {
  switch (unit) {
    case "SAR":
    case "SAR_mn":
    case "SAR million":
      return sar(value);
    case "%":
    case "fraction":
      return pct(value);
    case "pct_points":
      return pctPoints(value);
    case "bps":
      return bps(value);
    case "count":
      return count(value);
    case "x":
      return multiplier(value);
    default:
      return value === null || value === undefined ? "—" : grouped(value, Math.abs(value) < 10 ? 2 : 1);
  }
}

/**
 * A money TABLE column (UAT-05 / FMT01): the scale chosen ONCE from the
 * column's own values and stated once in the header ("EAD (SAR bn)"), cells
 * at that scale without a unit, and the raw SAR-million value kept for the
 * CSV under a header that says so. Input values are SAR million (number or
 * the server's decimal string).
 */
export function moneyCol(
  key: string,
  label: string,
  rows: Record<string, unknown>[],
): { key: string; label: string; csvLabel: string; align: "right"; format: (v: unknown) => string } {
  const values = rows.map((r) => (r[key] === null || r[key] === undefined || r[key] === "" ? null : Number(r[key])));
  const finite = values.filter((v): v is number => v !== null && Number.isFinite(v));
  const scale = columnScaleFor(finite);
  const decimals = decimalsFor(finite.map((v) => toScale(v, scale)));
  return {
    key,
    label: `${label} (${scale})`,
    csvLabel: `${label} (SAR million, raw)`,
    align: "right",
    format: (v: unknown) => {
      if (v === "N/A") return "N/A";
      const n = v === null || v === undefined || v === "" ? NaN : Number(v);
      return Number.isFinite(n) ? grouped(toScale(n, scale), decimals) : "—";
    },
  };
}

/**
 * FULL SAR for DATA TABLES (manual UAT finding 8, 2026-10-06).
 *
 * A displayed data table states the exact governed amount in SAR, not a
 * compacted multiple: the reader of a table is reconciling figures, and
 * "23.3" under a "(SAR bn)" header cannot be reconciled. The stored value is
 * SAR MILLION (manifest `amount_scale`), so DISPLAY multiplies by 1e6 and
 * nothing else: no rescaling per column, no abbreviation, no unit repeated in
 * the cell. The unit appears ONCE, in the column header.
 *
 * Nothing below touches a stored value, a calculation, a chart aggregation or
 * a raw export contract: these functions take the governed number and return
 * a string.
 */
const SAR_PER_MILLION = 1e6;

/**
 * Round a non-negative decimal STRING to `decimals`, half away from zero.
 *
 * Why a string, and not `grouped`'s `toPrecision(12)`: a full SAR amount
 * needs more than twelve significant digits. SAR 281,970,130,400.23 is
 * fourteen, so a twelve-figure guard rounded it to SAR 281,970,130,400 and
 * ERASED the halalas the table exists to show (coordinator review
 * S-REVIEW-01, 2026-10-06). There is no significant-digit ceiling here: the
 * rounding happens at the halala whatever the magnitude, and the carry is
 * done on the digits so no precision is lost to a float addition.
 *
 * `grouped` is unchanged and still serves the compact narrative and axis
 * formats, where values are small and the twelve-figure guard is right.
 */
function roundDecimalString(text: string, decimals: number): string {
  const [whole, frac = ""] = text.split(".");
  if (frac.length <= decimals) {
    const padded = frac.padEnd(decimals, "0");
    return decimals ? `${whole}.${padded}` : whole;
  }
  const chars = `${whole}${frac.slice(0, decimals)}`.split("");
  if (Number(frac[decimals]) >= 5) {
    let i = chars.length - 1;
    for (; i >= 0; i -= 1) {
      if (chars[i] === "9") {
        chars[i] = "0";
      } else {
        chars[i] = String(Number(chars[i]) + 1);
        break;
      }
    }
    if (i < 0) chars.unshift("1");
  }
  const digits = chars.join("");
  const cut = digits.length - decimals;
  const w = digits.slice(0, cut) || "0";
  return decimals ? `${w}.${digits.slice(cut)}` : w;
}

/**
 * Four guard digits below the halala. They absorb the float artifact of a
 * stored SAR-million value multiplied for display (5231.577413502459 million
 * is 5,231,577,413.502459 SAR, not …4999) while still letting a genuine
 * half -- 23.275 SAR, which a double holds as 23.27499999999999857… -- round
 * up to 23.28 rather than down.
 */
const GUARD_DIGITS = 4;

/** An exact SAR amount as a decimal string at `decimals`. Input: SAR million. */
function exactSar(valueInMillions: number, decimals: number): string {
  const abs = Math.abs(valueInMillions) * SAR_PER_MILLION;
  const rounded = roundDecimalString(abs.toFixed(decimals + GUARD_DIGITS), decimals);
  const [whole, frac] = rounded.split(".");
  const withSep = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const sign = valueInMillions < 0 && Number(rounded) !== 0 ? "\u2212" : "";
  return `${sign}${withSep}${frac ? `.${frac}` : ""}`;
}

/** Halala resolution, decided once for a whole column. */
function fullDecimalsFor(valuesInMillions: number[]): number {
  const finite = valuesInMillions.filter((v) => Number.isFinite(v) && v !== 0);
  if (!finite.length) return 0;
  // A real halala anywhere in the column means every cell shows halalas, so
  // the column reads at one resolution. The test is what the value ROUNDS to
  // at the halala -- not whether the double happens to be fractional, which
  // float noise makes true of almost every value.
  return finite.some((v) => !exactSar(v, 2).endsWith(".00")) ? 2 : 0;
}

/** One exact amount in SAR: "5,231,577,413.50". Input is SAR million. */
export function sarFull(valueInMillions: number | null | undefined, decimals = 2): string {
  if (valueInMillions === null || valueInMillions === undefined || !Number.isFinite(valueInMillions)) {
    return "\u2014";
  }
  return exactSar(valueInMillions, decimals);
}

/** A money TABLE column in full SAR: unit once in the header, exact cells. */
export function fullMoneyCol(
  key: string,
  label: string,
  rows: Record<string, unknown>[],
): { key: string; label: string; csvLabel: string; align: "right"; format: (v: unknown) => string } {
  const values = rows.map((r) => (r[key] === null || r[key] === undefined || r[key] === "" ? null : Number(r[key])));
  const finite = values.filter((v): v is number => v !== null && Number.isFinite(v));
  const decimals = fullDecimalsFor(finite);
  return {
    key,
    label: `${label} (SAR)`,
    // The CSV keeps the governed raw value and says so: an existing export
    // contract is not restated by a display change.
    csvLabel: `${label} (SAR million, raw)`,
    align: "right",
    format: (v: unknown) => {
      if (v === "N/A") return "N/A";
      if (v === null || v === undefined || v === "") return "\u2014";
      const n = Number(v);
      if (!Number.isFinite(n)) return "\u2014";
      return sarFull(n, decimals);
    },
  };
}

/** The data grid's variant: header suffix plus one cell string per value. */
export function fullMoneyColumn(valuesInMillions: (number | null)[]): {
  header: string;
  cells: string[];
} {
  const finite = valuesInMillions.filter((v): v is number => v !== null && Number.isFinite(v));
  const decimals = fullDecimalsFor(finite);
  return {
    header: "(SAR)",
    cells: valuesInMillions.map((v) => (v === null || !Number.isFinite(v) ? "\u2014" : sarFull(v, decimals))),
  };
}
