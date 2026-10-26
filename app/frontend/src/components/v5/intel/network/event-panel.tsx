"use client";

/**
 * PLAN_R13 §I Session IC (#8): the event translator panel. One line in ("oil falls 30% this morning", a pick), the
 * answer out: the ECL and Stage 2 hit, the names hit, who to call today. Drivers, assumptions and data limits fold.
 * Every figure from POST /api/v1/intel/network/event.
 */

import * as React from "react";

import { FromLink } from "@/components/v5/ui/back-link"; // R14 U (K1)

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Chip, Section, tableCls, tdCls, thCls } from "@/components/v5/dealdesk/kit";
import { Failed, Loading, Tiles, scrollCls } from "@/components/v5/dealdesk/products/parts";
import { cn } from "@/lib/utils";

import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeEvent, writeEventEmpty } from "@/lib/v5/plain-words-g/network";
import { networkApi } from "./api";
import { CHANNEL_LABEL, type EventRequest, type EventResult, FAMILY_PICKS, type Severity, bandTone, dsar, eventTiles, sar } from "./format";
import { Findings, Limits, SeveritySwitch } from "./parts";

const TITLE = "Event translator";

export function EventTranslatorPanel({ initialText = "", borrowerName, period, onOpenBorrower, autoRun = false }: {
  initialText?: string; borrowerName?: string; period?: string; onOpenBorrower?: (id: string) => void;
  /** R13 M: run the initial text at once (Noor's Ask hands the question over). */
  autoRun?: boolean;
}) {
  const [text, setText] = React.useState(initialText);
  const [severity, setSeverity] = React.useState<Severity>(
    () => (/\b(mild|moderate|severe)\b/i.exec(initialText)?.[1]?.toLowerCase() as Severity | undefined) ?? "moderate");
  const [state, setState] = React.useState<{ busy: boolean; data: EventResult | null; error: string }>({ busy: false, data: null, error: "" });
  const ac = React.useRef<AbortController | null>(null);

  const run = React.useCallback((req: EventRequest) => {
    ac.current?.abort();
    const c = new AbortController();
    ac.current = c;
    setState((s) => ({ ...s, busy: true, error: "" }));
    networkApi.event({ ...req, period }, c.signal)
      .then((data) => { if (!c.signal.aborted) setState({ busy: false, data, error: "" }); })
      .catch((err: unknown) => { if (!c.signal.aborted) setState({ busy: false, data: null, error: err instanceof Error ? err.message : "Could not translate the event." }); });
  }, [period]);
  React.useEffect(() => () => ac.current?.abort(), []);
  const started = React.useRef(false);
  React.useEffect(() => {
    if (!autoRun || started.current || !initialText.trim()) return;
    started.current = true;
    run({ text: initialText, severity });
  }, [autoRun, initialText, run, severity]);

  const pick = (family: string, preset: string) => {
    const t = preset || (family === "developer_delay"
      ? `${borrowerName ?? "Tuwaiq First Properties"} delays payments to contractors`
      : "Downgrade the construction sector");
    setText(t);
    run({ text: t, severity });
  };

  return (
    <Section title={TITLE} testId="intel-event"
             info={<>A shock this morning mapped to drivers, the borrowers it hits (directly and through suppliers, buyers and
               employers), the ECL and Stage 2 hit from the What-If engine, and who to call today.</>}>
      {!state.data && !state.busy ? <PanelWords panel="event-empty" lines={writeEventEmpty(FAMILY_PICKS.length)} /> : null}
      <form className="mb-3 flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) run({ text, severity }); }}>
        <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="What if oil falls 30% this morning?"
               aria-label="Describe the event" className="h-8 min-w-[220px] flex-1 text-[13px]" data-testid="intel-event-input" />
        <SeveritySwitch value={severity} onChange={setSeverity} testId="intel-event-severity" />
        <Button type="submit" size="sm" disabled={state.busy || !text.trim()} data-testid="intel-event-run">
          {state.busy ? "Translating…" : "Translate"}
        </Button>
      </form>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {FAMILY_PICKS.map((f) => (
          <button key={f.family} type="button" onClick={() => pick(f.family, f.text)} data-testid={`intel-event-pick-${f.family}`}
                  className="rounded-full border border-border px-2.5 py-0.5 text-[11px] text-text-secondary hover:bg-surface-hover">
            {f.label}
          </button>
        ))}
      </div>
      {state.busy && !state.data ? <Loading title={TITLE} testId="intel-event-loading" /> : null}
      {state.error ? <Failed title={TITLE} message={state.error} testId="intel-event-error" /> : null}
      {state.data ? <EventView r={state.data} onOpenBorrower={onOpenBorrower} /> : null}
    </Section>
  );
}

export function EventView({ r, onOpenBorrower }: { r: EventResult; onOpenBorrower?: (id: string) => void }) {
  return (
    <div data-testid="intel-event-result">
      <PanelWords panel="event" lines={() => writeEvent(r)} />
      <Findings text={r.text} testId="intel-event-findings" />
      <Tiles tiles={eventTiles(r)} testId="intel-event-tiles" />
      {r.call_list.length ? (
        <div className={cn(scrollCls, "mt-2")}>
          <table className={tableCls} data-testid="intel-event-calls">
            <thead><tr>{["Call", "Channel", "ECL", "Why", "The call"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>
              {r.call_list.map((c) => (
                <tr key={c.borrower_id}>
                  <td className={cn(tdCls, "max-w-[170px] truncate")} title={`${c.name} (${c.borrower_id}) · EAD ${sar(c.ead)}`}>
                    {onOpenBorrower && c.borrower_id.startsWith("CB")
                      ? <button type="button" className="text-accent hover:underline" onClick={() => onOpenBorrower(c.borrower_id)}>{c.name}</button>
                      : <FromLink className="text-accent hover:underline" href={c.href} from="event">{c.name}</FromLink>/* R14 U (K1) */}
                    {c.ews_band && c.ews_band !== "none" && c.ews_band !== "low"
                      ? <span className="ml-1"><Chip tone={bandTone(c.ews_band) === "negative" ? "negative" : "warning"}>{c.ews_band}</Chip></span> : null}
                    {c.rm ? <span className="block text-[11px] text-text-muted">RM {c.rm}{c.branch ? ` · ${c.branch}` : ""}</span> : null}
                  </td>
                  <td className={tdCls}>{CHANNEL_LABEL[c.channel] ?? c.channel}</td>
                  <td className={tdCls}>{dsar(c.d_ecl, 2)}</td>
                  <td className={cn(tdCls, "max-w-[260px] truncate whitespace-normal")} title={c.reason}>{c.reason}</td>
                  <td className={cn(tdCls, "max-w-[240px] whitespace-normal text-text-secondary")}>{c.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <details className="mt-3 rounded-md border border-border/70 px-3 py-2 text-[12px] text-text-secondary" data-testid="intel-event-drivers">
        <summary className="cursor-pointer font-medium">Drivers ({r.drivers.length})</summary>
        <ul className="mt-2 space-y-1 leading-5">
          {r.drivers.map((d, i) => (
            <li key={`${d.driver}-${d.scope}-${i}`}>
              <span className="font-medium text-text-primary">{d.label}: {d.value > 0 ? "+" : ""}{d.value} {d.unit}</span>
              <span className="text-text-muted"> · {d.scope} · {d.basis}</span>
              <span className="block">{d.assumption}</span>
            </li>
          ))}
        </ul>
      </details>
      <Limits assumptions={r.assumptions} limits={r.limits} calibration={r.calibration} lineage={r.lineage} testId="intel-event-limits" />
    </div>
  );
}
