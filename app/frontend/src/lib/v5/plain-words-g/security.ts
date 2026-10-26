/**
 * R14 G (K30, K34): the "In plain words" writer for Security value. Deterministic (N4).
 */
import type { Security } from "../../../components/v5/dealdesk/intel/approval/model.ts";
import { lines, pct, sar } from "./fmt.ts";

export function writeSecurity(s: Security): string[] {
  const what = "What each piece of security is worth to the bank, and the cheapest package that clears the hurdle";
  const ask = s.ask_package;
  let main: string;
  if (s.cheapest_package) {
    const c = s.cheapest_package;
    main = `Cheapest package that clears: ${c.text}, tying up ${sar(c.cost_sar_mn.value)} of the client's assets`
      + (ask ? ` against ${sar(ask.cost_sar_mn.value)} in the ask` : "");
  } else {
    const b = s.best_package;
    main = b ? `None of the client's own security clears: the best package reaches RAROC ${pct(b.lifetime_raroc.value, 1)}` : "None of the client's own security clears the hurdle";
  }
  const adds = (s.add_ons ?? []).filter((a) => a.on_ask_raroc?.value != null);
  const top = adds.slice().sort((a, b) => (b.on_ask_raroc!.value ?? 0) - (a.on_ask_raroc!.value ?? 0))[0];
  const article = top?.kind === "assignment" ? "the " : "a ";
  const lab = top ? `${article}${top.label.charAt(0).toLowerCase()}${top.label.slice(1)}` : "";
  const add = !top || (s.cheapest_package && !top.clears_on_ask) ? null
    : top.clears_on_ask ? `Adding ${lab} to the ask would clear, at RAROC ${pct(top.on_ask_raroc!.value, 1)}`
      : `Even adding ${lab} to the ask only reaches RAROC ${pct(top.on_ask_raroc!.value, 1)}`;
  const todo = s.needs_price ? "The rest has to come from price or structure: open Make it approvable below"
    : "Ask only for what clears; release the rest or keep it as headroom";
  return lines(what, main, add, todo);
}
