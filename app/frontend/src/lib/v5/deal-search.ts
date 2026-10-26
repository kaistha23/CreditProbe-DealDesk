/**
 * R14 U (K17): fuzzy search over the Deal Desk list, the same rules as backend/dealdesk/deal_list.py (score,
 * find_named), so the list filters as you type without a round trip and a deal named in the Ask box opens the deal.
 *
 *   dealScore("al sahal", "Al Sahel Building Materials Trading LLC", "R12-TWA")  → 0.765
 *   findNamedDeal("Why does Al Sahal fail?", rows)                              → the R12-TWA row
 */

export const STOP = new Set(`al el the and of for company co llc ltd limited est establishment trading group holding holdings
contracting industries industrial services national saudi arabian arabia modern united international commercial
general corporation corp inc limit limits renewal new project facility facilities proposal deal finance
working capital term loan line increase`.split(/\s+/));

export const PLACES = new Set(`riyadh jeddah dammam khobar makkah mecca madinah medina taif tabuk qassim hail jouf najran jazan jizan
yanbu jubail dhahran abha kharj unayzah buraidah qatif hofuf ahsa eastern northern southern western central najd red sea
gulf tihama asir baha qurayyat dawadmi rabigh khafji`.split(/\s+/));

export const THRESHOLD = 0.66;

export function norm(s: string): string {
  return (s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
}

function tokens(s: string): string[] {
  return norm(s).split(" ").filter(Boolean);
}

/** "R12-TWA" → "r12twa", "DD-06" → "dd6". */
export function idKey(pid: string): string {
  return (pid || "").toLowerCase().replace(/[^a-z0-9]/g, "").replace(/(?<=[a-z])0+(?=\d)/g, "");
}

/** difflib.SequenceMatcher(None, a, b).ratio(), for short words (same result as Python's for these inputs). */
export function ratio(a: string, b: string): number {
  if (!a.length && !b.length) return 1;
  const matches = matchCount(a, b);
  return (2 * matches) / (a.length + b.length);
}

function matchCount(a: string, b: string): number {
  // Ratcliff/Obershelp: longest common block, then recurse left and right (no junk heuristic: words are short).
  if (!a.length || !b.length) return 0;
  let bestI = 0, bestJ = 0, bestK = 0;
  for (let i = 0; i < a.length; i++) {
    for (let j = 0; j < b.length; j++) {
      let k = 0;
      while (i + k < a.length && j + k < b.length && a[i + k] === b[j + k]) k++;
      if (k > bestK) { bestI = i; bestJ = j; bestK = k; }
    }
  }
  if (!bestK) return 0;
  return bestK + matchCount(a.slice(0, bestI), b.slice(0, bestJ)) + matchCount(a.slice(bestI + bestK), b.slice(bestJ + bestK));
}

function tokSim(q: string, t: string): number {
  if (q === t) return 1;
  if (q.length >= 3 && t.startsWith(q)) return 0.95;
  if (q.length < 3) return 0;
  return ratio(q, t);
}

const round4 = (x: number) => Math.round(x * 10000) / 10000;

export function dealScore(query: string, name: string, pid: string, alt = ""): number {
  const q = norm(query);
  if (!q) return 0;
  const qk = idKey(q), ik = idKey(pid);
  if (qk && qk === ik) return 1;
  if (qk.length >= 3 && ik && (ik.includes(qk) || ik.endsWith(qk))) return 0.9;
  const words = [...tokens(name), ...tokens(alt)];
  if (!words.length) return 0;
  const qs = q.split(" ");
  const sims = qs.map((w) => {
    let best = Math.max(0, ...words.map((t) => tokSim(w, t)));
    if (STOP.has(w) && best < 1) best = best < 0.75 ? 0 : best;
    return best;
  });
  if (Math.min(...sims) < 0.75) return 0;
  if (qs.every((w) => STOP.has(w))) return 0;
  return round4((sims.reduce((a, b) => a + b, 0) / sims.length) * 0.85);
}

export interface DealRowLike { proposal_id: string; obligor_name: string; deal_name?: string }

/** Rows matching the query, best first (ties by id); the full list when the query is empty. */
export function searchDeals<R extends DealRowLike>(rows: R[], query: string): R[] {
  if (!norm(query)) return rows;
  return rows
    .map((r) => ({ r, s: dealScore(query, r.obligor_name, r.proposal_id, r.deal_name ?? "") }))
    .filter((x) => x.s >= THRESHOLD)
    .sort((a, b) => b.s - a.s || a.r.proposal_id.localeCompare(b.r.proposal_id))
    .map((x) => x.r);
}

/** The deal a free-text question names (an id anywhere, else the best 1–4 word run of a distinctive obligor name). */
export function findNamedDeal<R extends DealRowLike>(question: string, rows: R[]): R | null {
  const byKey = new Map(rows.map((r) => [idKey(r.proposal_id), r] as const));
  for (const m of (question || "").matchAll(/\b(?:DD|PL|R12)\s*-?\s*[A-Z0-9]{1,6}\b/gi)) {
    const r = byKey.get(idKey(m[0]));
    if (r) return r;
  }
  const words = tokens(question);
  let best: R | null = null, bestS = 0;
  for (const n of [4, 3, 2, 1]) {
    for (let i = 0; i + n <= words.length; i++) {
      const span = words.slice(i, i + n);
      if (span.every((w) => STOP.has(w) || PLACES.has(w)) || span.some((w) => w.length < 3 && !STOP.has(w))) continue;
      const phrase = span.join(" ");
      for (const r of rows) {
        let s = dealScore(phrase, r.obligor_name, "");
        if (n === 1 && s < 0.8) continue;
        s += 0.02 * n;
        if (s > bestS) { best = r; bestS = s; }
      }
    }
    if (best && bestS >= THRESHOLD + 0.02 * n) return best;
  }
  return bestS >= THRESHOLD ? best : null;
}
