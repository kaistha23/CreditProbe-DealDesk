/**
 * R14 G (K32, K34): the "In plain words" writer for the covenant designer. Deterministic (N4): same result, same words.
 * (1) what this is; (2) what it proposes, with the numbers that matter; (3) the caveat / what to do.
 */
import type { CovenantDesign, CovenantRow } from "../intel-ib.ts";
import { lines, pct, plural } from "./fmt.ts";

function level(r: CovenantRow): string {
  const t = r.proposed.threshold;
  return r.unit === "%" ? `${t.toFixed(0)}%` : `${t.toFixed(2)}x`;
}

function short(label: string): string {
  return label.replace(/\s*\(.*\)\s*$/, "");
}

export function writeCovenants(d: CovenantDesign): string[] {
  const mh = d.min_headroom_pct ?? 15;
  const rec = d.covenants.filter((c) => c.recommended);
  const what = "Covenant levels that would have warned 2+ quarters before trouble on similar borrowers";
  let propose: string;
  if (rec.length) {
    const top = rec.slice(0, 2).map((c) => `${short(c.label)} at ${level(c)}`).join(" and ");
    const best = rec[0];
    propose = `Set ${top}: early warning on ${pct(best.proposed.early_hit_rate)} of bad cases`
      + (best.proposed.deal_headroom_pct != null ? `, ${best.proposed.deal_headroom_pct.toFixed(0)}% cushion from today` : "");
  } else {
    propose = `No level both warns early and leaves the client ${mh.toFixed(0)}% cushion; keep the template and watch closely`;
  }
  const f = (d.findings ?? []).find((x) => x.kind === "template_too_tight") ?? (d.findings ?? [])[0];
  const caveat = f ? `The bank's standard ${f.title.replace(/^Template /, "").replace(/ is mis-calibrated:.*$/, "").replace(/ almost never warns:.*$/, "")} `
    + (f.kind === "template_too_tight"
      ? `fires on ${pct(d.covenants.find((c) => c.covenant === f.covenant)?.template?.false_alarm_rate)} of good borrowers: recalibrate it`
      : "almost never warns")
    : `${plural(d.covenants.length - rec.length, "covenant")} not recommended; the table says why`;
  const best = Math.max(0, ...d.covenants.map((c) => c.statistical_best?.early_hit_rate ?? c.proposed.early_hit_rate ?? 0));
  const partial = `Covenants catch at most ${pct(best)} early: keep Early Warning on the name`;
  return lines(what, propose, caveat, partial);
}
