"use client";

/**
 * PLAN_R13 §I Session IC (#9): the contagion map. If the named borrower fails, who else is hit, through which
 * channel, with the exposure, the amount at risk and the second-order ECL; drawn as a Plotly network.
 * Every figure from GET /api/v1/intel/network/contagion/{borrower}.
 */

import * as React from "react";

import { BorrowerNameLink } from "@/components/v5/ui/borrower-360-link"; // R14 U (K11)

import { Plot } from "@/components/v5/ews/plot";
import { Section, tableCls, tdCls, thCls } from "@/components/v5/dealdesk/kit";
import { useProduct } from "@/components/v5/dealdesk/products/api";
import { Failed, Loading, Tiles, scrollCls } from "@/components/v5/dealdesk/products/parts";
import { cn } from "@/lib/utils";

import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeContagion } from "@/lib/v5/plain-words-g/network";
import { networkApi } from "./api";
import { CHANNEL_LABEL, type ContagionResult, type Severity, contagionTiles, dsar, networkFigure, sar } from "./format";
import { Findings, Limits, SeveritySwitch } from "./parts";

const TITLE = "Contagion map";

export function ContagionPanel({ borrowerId, period, onOpenBorrower }: {
  borrowerId: string; period?: string; onOpenBorrower?: (id: string) => void;
}) {
  const [severity, setSeverity] = React.useState<Severity>("moderate");
  const { data, error, loading, reload } = useProduct(`contagion:${borrowerId}:${severity}:${period ?? ""}`,
    (s) => networkApi.contagion(borrowerId, severity, period, s));
  const action = <SeveritySwitch value={severity} onChange={setSeverity} testId="intel-contagion-severity" />;
  if (loading && !data) return <Loading title={TITLE} testId="intel-contagion-loading" />;
  if (error) return <Failed title={TITLE} message={error} onRetry={reload} testId="intel-contagion-error" />;
  if (!data) return null;
  return (
    <Section title={TITLE} testId="intel-contagion" action={action}
             info={<>If this borrower fails: second-order exposure through guarantees it gives, shared collateral, its group,
               its suppliers and buyers, and contractors paid by the same project employer. ECL from the What-If engine.</>}>
      <ContagionView r={data} onOpenBorrower={onOpenBorrower} />
    </Section>
  );
}

export function ContagionView({ r, onOpenBorrower }: { r: ContagionResult; onOpenBorrower?: (id: string) => void }) {
  const fig = React.useMemo(() => networkFigure(r), [r]);
  return (
    <div data-testid="intel-contagion-result">
      <PanelWords panel="contagion" lines={() => writeContagion(r)} source={r.data_domains?.note} />
      <Findings text={r.text} testId="intel-contagion-findings" />
      <Tiles tiles={contagionTiles(r)} testId="intel-contagion-tiles" />
      {r.network.nodes.length > 1 ? (
        <Plot data={fig.data} layout={fig.layout} height={360} testId="intel-contagion-network" filename="contagion-map"
              ariaLabel={`Contagion network around ${r.focal.name}: ${r.network.drawn} of ${r.network.available} linked names`}
              scrollZoom onPointClick={(id) => { if (onOpenBorrower && typeof id === "string" && id !== r.focal.borrower_id) onOpenBorrower(id); }} />
      ) : null}
      {r.names.length ? (
        <div className={cn(scrollCls, "mt-2")}>
          <table className={tableCls} data-testid="intel-contagion-names">
            <thead><tr>{["Borrower", "Channel", "Exposure", "At risk", "ECL", "Why"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>
              {r.names.slice(0, 10).map((n) => (
                <tr key={n.borrower_id}>
                  <td className={cn(tdCls, "max-w-[170px] truncate")} title={`${n.name} (${n.borrower_id}) · ${n.sector}`}>
                    {onOpenBorrower
                      ? <button type="button" className="text-accent hover:underline" onClick={() => onOpenBorrower(n.borrower_id)}>{n.name}</button>
                      : <BorrowerNameLink customerId={n.borrower_id} name={n.name} from="contagion" className="text-accent" />/* R14 U (K11) */}
                  </td>
                  <td className={tdCls}>{n.channels.map((c) => CHANNEL_LABEL[c] ?? c).join(", ")}</td>
                  <td className={tdCls}>{sar(n.exposure)}</td>
                  <td className={tdCls}>{sar(n.at_risk)}</td>
                  <td className={tdCls}>{dsar(n.d_ecl, 2)}</td>
                  <td className={cn(tdCls, "max-w-[240px] truncate")} title={n.why}>{n.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {r.names.length > 10 ? <p className="mt-1 text-[11px] text-text-muted">The 10 largest ECL changes of {r.totals.names} linked names.</p> : null}
        </div>
      ) : null}
      <Limits limits={r.limits} calibration={r.calibration} lineage={r.lineage} testId="intel-contagion-limits" />
    </div>
  );
}
