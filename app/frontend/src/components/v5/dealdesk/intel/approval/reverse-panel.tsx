"use client";

/**
 * R13 IA (backlog #4): the reverse solver. Why the deal fails, then the smallest change that makes it approvable as an
 * RM-ready counter-offer (copyable), and the other structures the Optimise engine found, closest first.
 */

import * as React from "react";

import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeReverse } from "@/lib/v5/plain-words-g/deal";
import { Chip, Section, SecondaryButton, tableCls, tdCls, thCls } from "../../kit";
import { useReverse } from "./api";
import { type Reverse, failureTone, pct } from "./model";
import { Answer, FigText, Loading } from "./parts";

export function ReverseView({ r }: { r: Reverse }) {
  const [copied, setCopied] = React.useState(false);
  const co = r.counter_offer;
  const copy = () => {
    if (!co) return;
    try {
      void navigator.clipboard.writeText(co.rm_text).then(() => setCopied(true), () => setCopied(false));
    } catch { setCopied(false); }
  };
  return (<>
    <Answer testId="ia-reverse-answer">{r.headline}</Answer>
    {r.failures.length ? (
      <div className="mt-2 flex flex-wrap gap-1.5">
        {r.failures.map((f, i) => <Chip key={i} tone={failureTone(f.kind)} title={f.text}>{f.label}</Chip>)}
      </div>) : null}
    {co ? (
      <div className="mt-3 rounded-md border border-accent/30 bg-accent-muted/40 p-3" data-testid="ia-counter-offer">
        <div className="mb-1 flex items-center gap-2">
          <h3 className="text-[12px] font-semibold uppercase tracking-[0.06em] text-text-secondary">Counter-offer</h3>
          <SecondaryButton className="ml-auto h-7" onClick={copy}>{copied ? "Copied" : "Copy for the RM"}</SecondaryButton>
        </div>
        <ul className="list-disc space-y-0.5 pl-5 text-[13px] text-text-primary">
          {co.changes.map((c) => <li key={c.field}>{c.text}</li>)}
        </ul>
        <div className="mt-2 text-[12px] text-text-secondary">
          <FigText f={co.lifetime_raroc}>RAROC {pct(r.ask.lifetime_raroc.value)} → {pct(co.lifetime_raroc.value)}</FigText>
          {" "}against <FigText f={r.ask.hurdle}>{pct(r.ask.hurdle.value)}</FigText> · approval {co.approval.level}
          {co.stress?.verdict ? ` · stress ${co.stress.verdict}` : ""}
        </div>
        {co.note ? <p className="mt-1 text-[12px] text-warning">{co.note}</p> : null}
      </div>) : null}
    {r.termless_blockers?.length ? <p className="mt-2 text-[12px] text-negative">{r.termless_blockers.join(" ")}</p> : null}
    {r.candidates.length > 1 ? (
      <details className="mt-3">
        <summary className="cursor-pointer text-[12px] font-medium text-text-secondary">Other structures ({r.candidates.length})</summary>
        <div className="mt-2 overflow-x-auto">
          <table className={tableCls}>
            <thead><tr><th className={thCls}>Lever</th><th className={thCls}>Change</th><th className={thCls}>RAROC</th><th className={thCls}>Stress</th></tr></thead>
            <tbody>{r.candidates.map((c, i) => (
              <tr key={i}>
                <td className={tdCls}>{c.label}</td>
                <td className={`${tdCls} whitespace-normal`}>{c.changes.map((x) => x.text).join("; ")}</td>
                <td className={tdCls}><FigText f={c.lifetime_raroc}>{pct(c.lifetime_raroc.value)}</FigText></td>
                <td className={tdCls}>{c.stress?.verdict ?? "not run"}</td>
              </tr>))}</tbody>
          </table>
        </div>
      </details>) : null}
  </>);
}

/** Deal page, More menu: "Make it approvable". */
export function ReverseSolverPanel({ proposalId }: { proposalId: string }) {
  const r = useReverse(proposalId);
  return (
    <Section title="Make it approvable" testId="ia-reverse-panel"
             info={<p>For a deal that fails the hurdle, a limit, a policy or the stress tier rule: the Optimise engine frees one lever family at a time
               (amount, tenor, security, price, covenants, then all) with everything else as asked, and returns the closest structure that clears.
               The closest one that also passes the stress ladder is the counter-offer.</p>}>
      <PanelWords panel="reverse" lines={r.data ? () => writeReverse(r.data!) : r.error ? [] : null} />
      {r.data ? <ReverseView r={r.data} /> : <Loading error={r.error} />}
    </Section>
  );
}
