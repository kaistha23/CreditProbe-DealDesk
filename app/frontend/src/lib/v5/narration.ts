/**
 * R16 n: the spoken narration of an answer (pure; node --test covers it).
 *
 * The Listen button on every answer plays a narration written for the ear, not the screen text read out:
 *
 *   1. the headline in one sentence
 *   2. the two or three numbers that matter, said naturally ("one point four eight billion riyals")
 *   3. where to look: the chart or table rendered with the answer ("In the chart on the right, the Construction bar
 *      stands well above the rest", "Look at the second row of the table: Tuwaiq Construction"), with a target so
 *      the screen can pulse the bar or row while it is said
 *   4. the suggested next step
 *
 * Deterministic: one writer per answer type (chart, table, figures, list, text), the next step per module. The DOM is
 * read in `narration-dom.ts`; this file only takes plain facts.
 */

import type { ActionBlock, ModuleKey } from "./thread-actions";

export type NarrationLang = "en" | "ar";
export type ChartKind = "bar" | "hbar" | "line" | "pie" | "waterfall" | "heatmap" | "scatter" | "other";
export type Place = "right" | "left" | "below" | "above";

export interface ChartSeries { name: string; labels: string[]; values: number[]; texts?: string[] }
export interface ChartFacts { kind: ChartKind; title: string; place: Place; series: ChartSeries[]; unit?: string; area?: number }
export interface TableFacts { title: string; columns: string[]; rows: string[][]; place: Place }

export interface NarrationInput {
  module: ModuleKey; question: string; lang: NarrationLang;
  blocks: ActionBlock[];
  charts?: ChartFacts[]; tables?: TableFacts[];
}

export type NarrationTarget =
  | { kind: "chart"; chart: number; series: number; point: number }
  | { kind: "row"; table: number; row: number };

export interface NarrationSegment { part: "headline" | "numbers" | "visual" | "next"; text: string; target?: NarrationTarget }
export type AnswerType = "chart" | "table" | "figures" | "list" | "text";
export interface Narration { type: AnswerType; lang: NarrationLang; segments: NarrationSegment[]; text: string }

// ------------------------------------------------------------------ language

const ARABIC = /[؀-ۿ]/g;
/** "ar" when the answer is written mostly in Arabic. */
export function answerLang(text: string): NarrationLang {
  const s = String(text ?? "");
  const letters = (s.match(/[A-Za-z؀-ۿ]/g) ?? []).length;
  if (!letters) return "en";
  return (s.match(ARABIC) ?? []).length / letters > 0.4 ? "ar" : "en";
}

// ------------------------------------------------------------------ numbers said naturally (English)

const ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
  "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"];
const TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];

function under1000(n: number): string {
  const h = Math.floor(n / 100), r = n % 100;
  const rest = r < 20 ? ONES[r] : TENS[Math.floor(r / 10)] + (r % 10 ? `-${ONES[r % 10]}` : "");
  if (!h) return rest;
  return `${ONES[h]} hundred${r ? ` and ${rest}` : ""}`;
}

/** 2450 → "two thousand four hundred and fifty" (integers below a trillion). */
export function intWords(n: number): string {
  n = Math.floor(Math.abs(n));
  if (n < 1000) return under1000(n);
  const parts: string[] = [];
  for (const [size, name] of [[1e9, "billion"], [1e6, "million"], [1e3, "thousand"]] as const) {
    if (n >= size) { parts.push(`${under1000(Math.floor(n / size))} ${name}`); n %= size; }
  }
  if (n) parts.push(n < 100 ? `and ${under1000(n)}` : under1000(n));
  return parts.join(" ");
}

/** "1.48" → "one point four eight"; "-3" → "minus three". */
export function numberWords(raw: string): string {
  const s = String(raw).replace(/,/g, "").trim();
  const neg = s.startsWith("-") || s.startsWith("−");
  const body = s.replace(/^[-−+]/, "");
  let [i, d] = body.split(".");
  if (d && d.length > 2) { const r = Number(`0.${d}`).toFixed(2); if (r.startsWith("1")) { i = String(Number(i || "0") + 1); d = ""; } else d = r.slice(2); }
  const whole = Number(i || "0");
  if (!Number.isFinite(whole)) return raw;
  let out = intWords(whole);
  const dd = (d ?? "").replace(/0+$/, "");
  if (dd) out += ` point ${dd.split("").map((c) => ONES[Number(c)] ?? c).join(" ")}`;
  return (neg ? "minus " : "") + out;
}

function yearWords(y: number): string {
  if (y >= 2000 && y < 2010) return `two thousand${y % 10 ? ` and ${ONES[y % 10]}` : ""}`;
  const hi = Math.floor(y / 100), lo = y % 100;
  return `${under1000(hi)} ${lo === 0 ? "hundred" : lo < 10 ? `oh ${ONES[lo]}` : under1000(lo)}`;
}

/** Large plain amounts said by scale: 1480000000 → "one point four eight billion". */
function scaled(n: number): string {
  const a = Math.abs(n);
  for (const [size, name] of [[1e9, "billion"], [1e6, "million"]] as const) {
    if (a >= size) {
      const v = +(n / size).toFixed(2);
      return `${numberWords(String(v))} ${name}`;
    }
  }
  return numberWords(String(+n.toFixed(2)));
}

const SCALE: Record<string, string> = { bn: "billion", b: "billion", billion: "billion", mn: "million", m: "million", mm: "million",
  million: "million", k: "thousand", thousand: "thousand", tn: "trillion", trillion: "trillion" };
const NUM = String.raw`[-−]?\d[\d,]*(?:\.\d+)?`;

/** The English text with every number said the way a person would say it. */
export function speakNumbers(text: string): string {
  let s = String(text ?? "");
  const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const ORDS = ["", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth",
    "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth", "twenty-first", "twenty-second", "twenty-third",
    "twenty-fourth", "twenty-fifth", "twenty-sixth", "twenty-seventh", "twenty-eighth", "twenty-ninth", "thirtieth", "thirty-first"];
  s = s.replace(/\b(20\d\d)-(\d\d)-(\d\d)\b/g, (m, y, mo, d) => (MONTHS[Number(mo) - 1] && ORDS[Number(d)] ? `the ${ORDS[Number(d)]} of ${MONTHS[Number(mo) - 1]} ${yearWords(Number(y))}` : m));
  s = s.replace(/\((\d+)d\)/g, (_m, n) => `(in ${n} days)`);
  s = s.replace(/\s*·\s*/g, ", ").replace(/\bBorrower 360\b/g, "Borrower three sixty");
  s = s.replace(/\bvs\.?(?=\s)/gi, "versus").replace(/\bYoY\b/g, "year on year").replace(/\bQoQ\b/g, "quarter on quarter").replace(/\be\.g\.\s?/gi, "for example, ");
  s = s.replace(/\b(20\d\d)\s?Q([1-4])\b/g, (_m, y, q) => `Q ${ONES[Number(q)]} ${yearWords(Number(y))}`);
  s = s.replace(/\bQ([1-4])\s?(20\d\d)\b/g, (_m, q, y) => `Q ${ONES[Number(q)]} ${yearWords(Number(y))}`);
  s = s.replace(new RegExp(String.raw`(${NUM})\s?(mn|mm|m|million)\b`, "gi"), (m, n) => {
    const v = Number(String(n).replace(/,/g, "").replace("−", "-"));
    return Math.abs(v) >= 1000 ? `${+(v / 1000).toFixed(2)} bn` : m;
  });
  s = s.replace(new RegExp(String.raw`(?:\bSAR|\bSR|﷼)\s?(${NUM})\s?(bn|billion|b|mn|mm|m|million|k|thousand)?\b`, "gi"), (_m, n, sc) =>
    `${sc ? `${numberWords(n)} ${SCALE[sc.toLowerCase()]}` : Math.abs(Number(String(n).replace(/,/g, ""))) >= 1e6 ? scaled(Number(String(n).replace(/,/g, ""))) : numberWords(n)} riyals`);
  s = s.replace(new RegExp(String.raw`(${NUM})\s?(bn|mn|mm|tn)\b`, "gi"), (_m, n, sc) => `${numberWords(n)} ${SCALE[sc.toLowerCase()]}`);
  s = s.replace(new RegExp(String.raw`(${NUM})\s?(billion|million|thousand)\b`, "gi"), (_m, n, sc) => `${numberWords(n)} ${sc.toLowerCase()}`);
  s = s.replace(new RegExp(String.raw`(${NUM})\s?(?:pp|p\.p\.)(?![a-z])`, "gi"), (_m, n) => `${numberWords(n)} percentage points`);
  s = s.replace(new RegExp(String.raw`(${NUM})\s?%`, "g"), (_m, n) => `${numberWords(n)} percent`);
  s = s.replace(new RegExp(String.raw`(${NUM})\s?bps\b`, "gi"), (_m, n) => `${numberWords(n)} basis points`);
  s = s.replace(new RegExp(String.raw`(${NUM})\s?x\b`, "g"), (_m, n) => `${numberWords(n)} times`);
  s = s.replace(/\b(19\d\d|20\d\d)\b/g, (_m, y) => yearWords(Number(y)));
  s = s.replace(/(^|[\s(])\+(?=\d)/g, "$1plus ");
  s = s.replace(new RegExp(String.raw`(?<![\w.]|[A-Za-z][-−])(${NUM})(?![\w]|\.\d)`, "g"), (_m, n) => {
    const v = Number(String(n).replace(/,/g, "").replace("−", "-"));
    return Math.abs(v) >= 1e6 ? scaled(v) : numberWords(n);
  });
  return s.replace(/\s+/g, " ").trim();
}

// ------------------------------------------------------------------ text helpers

const hasNumber = (s: string) => /\d/.test(s);
const plain = (s: string) => String(s ?? "").replace(/\s*\([^()]*[÷×=][^()]*\)/g, "").replace(/^#+\s*/, "").replace(/\*\*|__|`/g, "").replace(/\s+/g, " ").trim();

function sentences(text: string): string[] {
  return plain(text).split(/(?<=[.!?؟])\s+(?=[A-Z0-9"'(؀-ۿ])/).map((x) => x.trim()).filter((x) => x.length > 1);
}

function shorten(s: string, words = 30): string {
  const w = s.split(/\s+/);
  if (w.length <= words) return s;
  let cut = w.slice(0, words).join(" ");
  if ((cut.match(/\(/g) ?? []).length > (cut.match(/\)/g) ?? []).length) cut = cut.slice(0, cut.lastIndexOf("(")).trim();
  const at = Math.max(cut.lastIndexOf(","), cut.lastIndexOf(";"));
  return `${(at > cut.length / 2 ? cut.slice(0, at) : cut).replace(/[,;:]$/, "")}.`;
}

const end = (s: string) => { const t = s.replace(/[\s:;,–—-]+$/, ""); return /[.!?؟]$/.test(t) ? t : `${t}.`; };
const cap = (s: string) => (s.charAt(0).toUpperCase() + s.slice(1)).replace(/([.!?]\s+)([a-z])/g, (_m, a, b) => a + b.toUpperCase());

function textsOf(blocks: ActionBlock[]): string[] {
  const out: string[] = [];
  for (const b of blocks) {
    if (b.kind === "text") { for (const line of b.text.split("\n")) if (!line.startsWith("###")) out.push(...sentences(line)); }
    else if (b.kind === "bullets") out.push(...b.items.map(plain));
  }
  return out;
}

const NEXT_RX = /\b(next step|suggest|recommend|you could|you may want|consider|we should|worth (?:checking|looking)|ask (?:me|noor)|open the)\b|الخطوة التالية|ننصح|يُقترح/i;

// ------------------------------------------------------------------ the parts

const NEXT: Record<ModuleKey, [string, string]> = {
  cockpit: ["Next, ask a follow-up, or share this answer with a colleague.", "الخطوة التالية: اطرح سؤال متابعة، أو شارك هذه الإجابة مع زميل."],
  noor: ["Next, ask Noor why, or what you could do about it.", "الخطوة التالية: اسأل نور عن السبب، أو عمّا يمكن فعله."],
  dealdesk: ["Next, open the proposal and check its limits and pricing.", "الخطوة التالية: افتح المقترح وراجع حدوده وتسعيره."],
  whatif: ["Next, try another scenario to see how far the provision moves.", "الخطوة التالية: جرّب سيناريو آخر لترى مدى تغيّر المخصص."],
  lenses: ["Next, open the lens to see the borrowers behind these figures.", "الخطوة التالية: افتح العدسة لترى المقترضين وراء هذه الأرقام."],
  ews: ["Next, open the customers on the watch list and triage them.", "الخطوة التالية: افتح العملاء في قائمة المراقبة وصنّفهم."],
  b360: ["Next, open the linked parties to see who else is exposed.", "الخطوة التالية: افتح الأطراف المرتبطة لترى من يتعرض أيضاً."],
  scorecard: ["Next, go through the findings and decide which to fix first.", "الخطوة التالية: راجع الملاحظات وقرّر أيها يُعالج أولاً."],
  playbook: ["Next, add this answer to your report.", "الخطوة التالية: أضف هذه الإجابة إلى تقريرك."],
  intel: ["Next, open the sources to check the figures behind this panel.", "الخطوة التالية: افتح المصادر لتتحقق من الأرقام."],
  agents: ["Next, review the agent's findings and approve the actions you agree with.", "الخطوة التالية: راجع نتائج الوكيل ووافق على الإجراءات المناسبة."],
};

const PLACE_EN: Record<Place, string> = { right: "on the right", left: "on the left", below: "below", above: "above" };
const PLACE_AR: Record<Place, string> = { right: "على اليمين", left: "على اليسار", below: "في الأسفل", above: "في الأعلى" };
const ORD_EN = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"];
const ORD_AR = ["الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس", "السابع", "الثامن", "التاسع", "العاشر"];

function compact(v: number, unit = ""): string {
  const a = Math.abs(v);
  const n = a >= 1e9 ? `${+(v / 1e9).toFixed(2)} bn` : a >= 1e6 ? `${+(v / 1e6).toFixed(2)} mn` : a >= 1e4 ? `${Math.round(v).toLocaleString("en-US")}` : `${+v.toFixed(2)}`;
  if (unit === "%") return `${n}%`;
  if (unit.startsWith("SAR ")) return `SAR ${+v.toFixed(2)} ${unit.slice(4)}`;
  if (unit === "SAR") return `SAR ${n}`;
  return unit ? `${n} ${unit}` : n;
}

function valueText(s: ChartSeries, i: number, unit?: string): string {
  const t = plain(s.texts?.[i] ?? "");
  if (t && hasNumber(t) && t.length < 24) return t;
  return compact(s.values[i], unit);
}

function topOf(values: number[]): { i: number; second: number; ratio: number } {
  let i = -1, j = -1;
  values.forEach((v, k) => {
    if (!Number.isFinite(v)) return;
    if (i < 0 || Math.abs(v) > Math.abs(values[i])) { j = i; i = k; }
    else if (j < 0 || Math.abs(v) > Math.abs(values[j])) j = k;
  });
  const a = i >= 0 ? Math.abs(values[i]) : 0, b = j >= 0 ? Math.abs(values[j]) : 0;
  return { i, second: j, ratio: b > 0 ? a / b : a > 0 ? Infinity : 1 };
}

/** The sentence that points at the chart, and the element to pulse while it is said. */
export function chartLine(c: ChartFacts, index: number, lang: NarrationLang): NarrationSegment | null {
  const s = c.series.find((x) => x.values.some(Number.isFinite) && x.labels.length) ?? c.series[0];
  const si = Math.max(0, c.series.indexOf(s));
  const en = lang === "en";
  const where = en ? PLACE_EN[c.place] : PLACE_AR[c.place];
  const title = plain(c.title);
  if (!s || !s.values.length) {
    return { part: "visual", target: { kind: "chart", chart: index, series: 0, point: -1 },
      text: en ? `The chart ${where}${title ? `, ${title},` : ""} shows this at a glance.` : `الرسم البياني ${where}${title ? ` (${title})` : ""} يوضح ذلك بنظرة واحدة.` };
  }
  const label = (i: number) => plain(s.labels[i] ?? "") || (en ? `item ${i + 1}` : `البند ${i + 1}`);
  if (c.kind === "line" || c.kind === "scatter") {
    const ok = s.values.map((v, i) => [v, i] as const).filter(([v]) => Number.isFinite(v));
    if (ok.length >= 2) {
      const [a, ia] = ok[0], [b, ib] = ok[ok.length - 1];
      const move = Math.abs(b - a) <= Math.abs(a) * 0.02 ? (en ? "holds steady" : "يبقى مستقراً") : b > a ? (en ? "rises" : "يرتفع") : (en ? "falls" : "ينخفض");
      const short = (x: string) => { const t = plain(x).split(/[:(]/)[0].trim(); return t.length && t.length <= 40 ? t : ""; };
      const name = short(s.name) || short(title) || (en ? "the line" : "الخط");
      const indexed = s.labels.every((l, k) => plain(l) === String(k)) || s.labels.every((l) => !plain(l));
      if (indexed) {
        return { part: "visual", target: { kind: "chart", chart: index, series: si, point: ib },
          text: en ? `In the line chart ${where}, ${name} ${move} from ${valueText(s, ia, c.unit)} to ${valueText(s, ib, c.unit)} over the last ${ok.length} periods.`
                   : `في الرسم البياني ${where}، ${name} ${move} من ${valueText(s, ia, c.unit)} إلى ${valueText(s, ib, c.unit)} خلال آخر ${ok.length} فترات.` };
      }
      return { part: "visual", target: { kind: "chart", chart: index, series: si, point: ib },
        text: en ? `In the line chart ${where}, ${name} ${move} from ${valueText(s, ia, c.unit)} in ${label(ia)} to ${valueText(s, ib, c.unit)} in ${label(ib)}.`
                 : `في الرسم البياني ${where}، ${name} ${move} من ${valueText(s, ia, c.unit)} في ${label(ia)} إلى ${valueText(s, ib, c.unit)} في ${label(ib)}.` };
    }
  }
  const top = topOf(s.values);
  if (top.i < 0) return null;
  const v = valueText(s, top.i, c.unit);
  const target: NarrationTarget = { kind: "chart", chart: index, series: si, point: top.i };
  if (c.kind === "pie") {
    const total = s.values.reduce((x, y) => x + (Number.isFinite(y) ? Math.abs(y) : 0), 0);
    const pct = total ? Math.round((Math.abs(s.values[top.i]) / total) * 100) : 0;
    return { part: "visual", target, text: en ? `In the chart ${where}, the largest slice is ${label(top.i)}, ${pct}% of the total.`
                                             : `في الرسم البياني ${where}، أكبر شريحة هي ${label(top.i)} بنسبة ${pct}% من الإجمالي.` };
  }
  if (c.kind === "waterfall") {
    return { part: "visual", target, text: en ? `In the waterfall ${where}, the biggest step is ${label(top.i)}, at ${v}.`
                                             : `في الرسم الشلالي ${where}، أكبر خطوة هي ${label(top.i)} عند ${v}.` };
  }
  if (c.kind === "bar" || c.kind === "hbar") {
    const tall = c.kind === "hbar" ? "longest" : "tallest";
    if (s.values.length === 1) return { part: "visual", target, text: en ? `In the chart ${where}, the ${label(top.i)} bar shows ${v}.` : `في الرسم البياني ${where}، يُظهر عمود ${label(top.i)} القيمة ${v}.` };
    if (top.ratio >= 1.5) {
      return { part: "visual", target, text: en ? `In the chart ${where}, the ${label(top.i)} bar stands well above the rest, at ${v}.`
                                               : `في الرسم البياني ${where}، يبرز عمود ${label(top.i)} بوضوح فوق البقية عند ${v}.` };
    }
    return { part: "visual", target, text: en ? `In the chart ${where}, the ${label(top.i)} bar is the ${tall}, at ${v}, followed by ${label(top.second)}.`
                                             : `في الرسم البياني ${where}، عمود ${label(top.i)} هو الأعلى عند ${v}، يليه ${label(top.second)}.` };
  }
  return { part: "visual", target, text: en ? `In the chart ${where}${title ? `, ${title}` : ""}, look at ${label(top.i)}: ${v}.`
                                           : `في الرسم البياني ${where}${title ? ` (${title})` : ""}، انظر إلى ${label(top.i)}: ${v}.` };
}

const NUMERIC_CELL = /^[^\p{L}\d]*(?:SAR|SR|﷼)?\s*[-−+]?\d[\d,]*(?:\.\d+)?\s*(?:%|bn|mn|m|k|x|bps|pp|billion|million|thousand|riyals?|مليار|مليون)?[^\p{L}\d]*$/iu;
const num = (s: string) => {
  if (!NUMERIC_CELL.test(String(s ?? "").trim())) return NaN;
  const m = /[-−]?\d[\d,]*(?:\.\d+)?/.exec(String(s ?? ""));
  if (!m) return NaN;
  let v = Number(m[0].replace(/,/g, "").replace("−", "-"));
  if (/\bbn\b|billion|مليار/i.test(s)) v *= 1e9; else if (/\bmn\b|\bm\b|million|مليون/i.test(s)) v *= 1e6; else if (/\bk\b|thousand/i.test(s)) v *= 1e3;
  return v;
};

/** The row of the table worth looking at: the largest figure in its first numeric column (else the first row). */
export function tableLine(t: TableFacts, index: number, lang: NarrationLang): NarrationSegment | null {
  if (!t.rows.length) return null;
  const en = lang === "en";
  const skipCol = (h: string) => /^(#|no\.?|rank|id|rating|grade|stage|year|period|date|quarter)$/i.test(plain(h));
  let col = -1;
  for (let c = 1; c < Math.max(...t.rows.map((r) => r.length)); c += 1) {
    if (skipCol(t.columns[c] ?? "")) continue;
    const ok = t.rows.filter((r) => Number.isFinite(num(r[c] ?? ""))).length;
    if (ok >= Math.max(1, Math.ceil(t.rows.length * 0.6))) { col = c; break; }
  }
  let row = 0;
  if (col > 0 && t.rows.length > 1) {
    let best = -Infinity;
    t.rows.forEach((r, i) => { const v = Math.abs(num(r[col] ?? "")); if (Number.isFinite(v) && v > best) { best = v; row = i; } });
  }
  const cell = t.rows[row].find((c, i) => i !== col && plain(c) && !Number.isFinite(num(c))) ?? t.rows[row][0] ?? "";
  const name = plain(cell).split(/\s+/).slice(0, 6).join(" ").replace(/[·,;:]$/, "") || (en ? "this row" : "هذا الصف");
  const head = col > 0 ? plain(t.columns[col] ?? "").replace(/\s*\([^)]*\)\s*/g, " ").trim() : "";
  const val = col > 0 ? plain(t.rows[row][col] ?? "") : "";
  const ord = en ? (ORD_EN[row] ?? `number ${row + 1}`) : (ORD_AR[row] ?? `رقم ${row + 1}`);
  const where = t.place === "right" ? (en ? " on the right" : " على اليمين") : "";
  const target: NarrationTarget = { kind: "row", table: index, row };
  if (en) return { part: "visual", target, text: `Look at the ${ord} row of the table${where}: ${name}${val ? `, with ${head ? `${/[A-Z]{2,}/.test(head) ? head : head.toLowerCase()} of ` : ""}${val}` : ""}.` };
  return { part: "visual", target, text: `انظر إلى الصف ${ord} في الجدول${where}: ${name}${val ? `، ${head ? `${head} ` : ""}${val}` : ""}.` };
}

function figuresOf(blocks: ActionBlock[]): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];
  for (const b of blocks) if (b.kind === "figures") for (const f of b.items) if (hasNumber(f.value) && f.label) out.push({ label: plain(f.label), value: plain(f.value) });
  return out;
}

export function answerType(inp: NarrationInput): AnswerType {
  if (inp.charts?.length) return "chart";
  if (inp.tables?.length || inp.blocks.some((b) => b.kind === "table")) return "table";
  if (figuresOf(inp.blocks).length) return "figures";
  if (inp.blocks.some((b) => b.kind === "bullets")) return "list";
  return "text";
}

/** Tables from the blocks when the reader found none on screen (tests; answers whose table is not a <table>). */
function tablesOf(inp: NarrationInput): TableFacts[] {
  if (inp.tables?.length) return inp.tables;
  return inp.blocks.filter((b): b is Extract<ActionBlock, { kind: "table" }> => b.kind === "table")
    .map((b) => ({ title: b.title, columns: b.columns, rows: b.rows.map((r) => r.map(String)), place: "below" as Place }));
}

// ------------------------------------------------------------------ the writer

/** The narration of one answer: headline, the numbers, where to look, the next step. */
export function narrate(inp: NarrationInput): Narration {
  const lang = inp.lang;
  const en = lang === "en";
  const type = answerType(inp);
  const lines = textsOf(inp.blocks);
  const nextIdx = lines.findIndex((l) => NEXT_RX.test(l) && l.split(/\s+/).length >= 5);
  const body = lines.filter((_l, i) => i !== nextIdx);
  const segs: NarrationSegment[] = [];

  // 1. headline
  const isMeta = (l: string) => { const p = l.split(/\s*·\s*/); return p.length >= 3 && p.every((x) => x.split(/\s+/).length <= 5); };
  const isLabel = (l: string) => l.replace(/[.:]$/, "").split(/\s+/).length < 4 || isMeta(l);
  while (body.length > 1 && isLabel(body[0])) body.shift();
  const headline = body[0] ? cap(shorten(end(body[0]), 32)) : en ? `Here is the answer to: ${plain(inp.question) || "your question"}.` : `هذه إجابة سؤالك: ${plain(inp.question)}.`;
  segs.push({ part: "headline", text: headline });

  // 3. visual (worked out first so the numbers do not repeat it)
  const visuals: NarrationSegment[] = [];
  // the main chart: the largest on screen (sparklines and small multiples are not read one by one)
  const charts = inp.charts ?? [];
  const main = charts.reduce((b, c, i) => ((c.area ?? 0) > (charts[b]?.area ?? 0) ? i : b), 0);
  if (charts[main]) { const l = chartLine(charts[main], main, lang); if (l) visuals.push(l); }
  const tables = tablesOf(inp);
  if (visuals.length < 2 && tables.length) { const l = tableLine(tables[0], 0, lang); if (l) visuals.push(l); }

  // 2. the numbers that matter (two or three, counting the headline's)
  let numbers = (headline.match(/\d[\d,.]*/g) ?? []).length;
  const said: string[] = [];
  const figs = figuresOf(inp.blocks);
  if (figs.length && numbers < 3) {
    const pick = figs.slice(0, Math.max(2, 3 - numbers)).slice(0, 3);
    said.push(en ? `${pick.map((f, i) => `${i === 0 ? "" : i === pick.length - 1 ? "and " : ""}${i === 0 || /^[A-Z0-9]{2,}\b/.test(f.label) ? f.label : f.label[0].toLowerCase() + f.label.slice(1)} is ${f.value}`).join(pick.length > 2 ? ", " : " ")}.`
                 : `${pick.map((f) => `${f.label}: ${f.value}`).join("، ")}.`);
    numbers += pick.length;
  }
  for (const l of body.slice(1)) {
    if (numbers >= 2 || said.length >= 2) break;
    if (!hasNumber(l) || l.length > 220) continue;
    said.push(shorten(end(l), 28));
    numbers += Math.min(2, (l.match(/\d[\d,.]*/g) ?? []).length);
  }
  if (!numbers && !said.length && !visuals.some((v) => hasNumber(v.text))) {
    const t = tables[0];
    if (t?.rows.length) said.push(en ? `The table has ${t.rows.length} rows.` : `يضم الجدول ${t.rows.length} صفوف.`);
  }
  for (const s of said) segs.push({ part: "numbers", text: s });
  segs.push(...visuals);

  // 4. the next step: the answer's own, else the module's
  const own = nextIdx >= 0 ? shorten(end(lines[nextIdx]), 26) : "";
  segs.push({ part: "next", text: own ? (en && !/^next\b/i.test(own) ? `Next step: ${own}` : own) : NEXT[inp.module][en ? 0 : 1] });

  const spoken = segs.map((s) => ({ ...s, text: en ? cap(speakNumbers(s.text)) : s.text }));
  return { type, lang, segments: spoken, text: spoken.map((s) => s.text).join(" ") };
}
