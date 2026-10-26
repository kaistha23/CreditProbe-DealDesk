"use client";

/**
 * PLAN_R6 D4: the (i) behind every Deal Desk chart, written for someone who
 * has never structured a deal. Each explainer has the same four parts: what
 * the chart shows, each component's formula with this deal's numbers, how to
 * read it, and what to do with it.
 *
 * PLAN_R12 G (R11_FEEDBACK I6): the Deal Desk (i) popover itself. Same props as the shared InfoPopover, but the panel is
 * opaque, rendered fixed in a portal on <body> (above every table, chart and card), placed collision-aware (below the (i)
 * when it fits, else above; shifted sideways into the viewport) with a max width and wrapping, and scrolls inside
 * when taller than the room. Placement is the pure, tested `placePanel` (lib/v5/dealdesk-popover.ts).
 */

import * as React from "react";
import { createPortal } from "react-dom";
import { Info, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { type Placement, PANEL_MAX_WIDTH, placePanel } from "@/lib/v5/dealdesk-popover";
import type { Analysis, Constraint, Grid, OptimizeResult, StressResult, Terms, Tornado } from "@/lib/v5/dealdesk";
import { bps, constraintRead, gridX, money, rate } from "@/lib/v5/dealdesk";

export function InfoPopover({ title, children, className, align = "left", testId }: {
  title?: string; children: React.ReactNode; className?: string; align?: "left" | "right"; testId?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [place, setPlace] = React.useState<Placement | null>(null);
  const btn = React.useRef<HTMLButtonElement>(null);
  const panel = React.useRef<HTMLDivElement>(null);
  const id = React.useId();

  const measure = React.useCallback(() => {
    const b = btn.current?.getBoundingClientRect();
    if (!b) return;
    const el = panel.current;
    const size = { width: el ? Math.min(el.scrollWidth, PANEL_MAX_WIDTH) || PANEL_MAX_WIDTH : PANEL_MAX_WIDTH, height: el ? el.scrollHeight : 320 };
    // the layout viewport, without the scrollbars (innerWidth counts a vertical scrollbar the panel would sit under)
    // (in this app the body carries the page's scrollbar: its clientWidth is the width a panel may use)
    const de = document.documentElement;
    const w = Math.min(de.clientWidth || window.innerWidth, document.body?.clientWidth || window.innerWidth, window.innerWidth);
    setPlace(placePanel(b, size, { width: w, height: Math.min(de.clientHeight || window.innerHeight, window.innerHeight) }, align));
  }, [align]);

  const close = React.useCallback(() => { setOpen(false); setPlace(null); }, []);
  React.useLayoutEffect(() => {
    if (!open) return;
    let second = 0;
    const first = requestAnimationFrame(() => { measure(); second = requestAnimationFrame(measure); }); // then with the real height
    return () => { cancelAnimationFrame(first); cancelAnimationFrame(second); };
  }, [open, measure]);

  React.useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!btn.current?.contains(t) && !panel.current?.contains(t)) close();
    };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { close(); btn.current?.focus(); } };
    const move = () => measure();
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    window.addEventListener("resize", move);
    window.addEventListener("scroll", move, true);
    return () => {
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", key);
      window.removeEventListener("resize", move);
      window.removeEventListener("scroll", move, true);
    };
  }, [open, measure, close]);

  return (
    <span className={cn("relative inline-flex", className)}>
      <button ref={btn} type="button" onClick={() => (open ? close() : setOpen(true))} aria-expanded={open} aria-controls={open ? id : undefined}
              aria-label={open ? "Hide the explanation" : `About ${title ?? "this screen"}`} data-testid={testId ?? "dd-info"}
              className={cn("inline-flex size-5 items-center justify-center rounded-full border transition-colors",
                            open ? "border-accent text-accent" : "border-border text-text-muted hover:border-border-strong hover:text-text-secondary")}>
        <Info className="size-3" aria-hidden />
      </button>
      {open && typeof document !== "undefined" ? createPortal(
        <div ref={panel} id={id} role="dialog" aria-label={title ?? "About this screen"} data-testid="dd-info-panel" data-side={place?.side ?? ""}
             style={{ position: "fixed", top: place?.top ?? -9999, left: place?.left ?? -9999, width: place?.width ?? PANEL_MAX_WIDTH,
                      maxHeight: place?.maxHeight, visibility: place ? "visible" : "hidden", zIndex: 1000 }}
             className="overflow-y-auto overscroll-contain rounded-lg border border-border bg-surface-raised p-4 text-left shadow-xl [overflow-wrap:anywhere]">
          <div className="flex items-start justify-between gap-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">{title ?? "About this screen"}</p>
            <button type="button" onClick={close} aria-label="Close"
                    className="-mr-1 -mt-1 rounded p-1 text-text-muted transition-colors hover:bg-surface-hover hover:text-text-primary">
              <X className="size-3" aria-hidden /></button>
          </div>
          <div className="mt-2 space-y-2 whitespace-normal text-xs font-normal normal-case leading-relaxed tracking-normal text-text-secondary">{children}</div>
        </div>, document.body) : null}
    </span>
  );
}

function Part({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-2 first:mt-0">
      <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">{title}</p>
      <div className="mt-0.5 space-y-1 text-[12px] leading-5 text-text-secondary">{children}</div>
    </div>
  );
}

export function Explainer({ shows, formulas, read, act, testId }: {
  shows: React.ReactNode; formulas: React.ReactNode[]; read: React.ReactNode; act: React.ReactNode; testId?: string;
}) {
  return (
    <div data-testid={testId}>
      <Part title="What it shows">{shows}</Part>
      <Part title="How each part is worked out">
        <ul className="list-disc space-y-1 pl-4">{formulas.map((f, i) => <li key={i}>{f}</li>)}</ul>
      </Part>
      <Part title="How to read it">{read}</Part>
      <Part title="What to do with it">{act}</Part>
    </div>
  );
}

const step = (res: Analysis, needle: RegExp) => res.waterfall.find((b) => needle.test(b.step))?.value;

export function WaterfallInfo({ res }: { res: Analysis }) {
  const m = res.metrics;
  const v = (re: RegExp) => money(step(res, re) ?? null);
  return <Explainer testId="dealdesk-info-waterfall"
    shows={<p>Where the deal&apos;s profit comes from and where it goes, over its whole life, each bar in present value (future years discounted at the {rate(m.hurdle)} hurdle).</p>}
    formulas={[
      <>Profit income {v(/profit income/i)}: drawn balance × (3M SAIBOR or SOFR + {bps(res.terms.margin_bps)} margin), each year.</>,
      <>Fees {v(/fee/i)}: the {bps(res.terms.upfront_fee_bps)} upfront fee on the amount, spread over the life, plus commitment fees.</>,
      <>FTP {v(/ftp|funding/i)}: what treasury charges for the money, the base rate plus a liquidity premium for the tenor.</>,
      <>Opex {v(/opex|cost to/i)}: origination, servicing and covenant monitoring.</>,
      <>Expected loss {v(/el|loss/i)}: EAD × PD × LGD each year; year-1 PD {rate(m.pd_12m, 2)}, LGD {rate(m.lgd_y1)}, EAD {money(m.ead_y1)}.</>,
      <>Capital benefit {v(/capital benefit/i)}: 5% earned on the capital held; zakat {v(/zakat/i)}: 10% of pre-zakat profit.</>,
      <>Risk-adjusted profit {v(/risk-adjusted|rap/i)} ÷ capital (PV) = lifetime RAROC {rate(m.lifetime_raroc)}.</>,
    ]}
    read={<p>Green bars add profit, red bars take it away; the last bar is what is left. RAROC {rate(m.lifetime_raroc)} against the {rate(m.hurdle)} hurdle: {m.clears_hurdle ? "the deal clears" : "the deal falls short"}; SVA {money(m.sva)}.</p>}
    act={<p>The biggest red bar is the cost to attack. Large EL: add collateral or a guarantee. Large FTP against thin income: reprice the margin (breakeven {m.breakeven_margin_bps === null ? "–" : bps(m.breakeven_margin_bps)}) or shorten the tenor.</p>} />;
}

export function HeatmapInfo({ grid, ask }: { grid: Grid; ask: Terms }) {
  const xs = gridX(grid);
  const lever = grid.x === "commission_bps" ? "commission" : "margin";
  const askX = grid.ask?.x ?? (lever === "commission" ? ask.commission_bps : ask.margin_bps);
  return <Explainer testId="dealdesk-info-heatmap"
    shows={<p>Lifetime RAROC for every combination of {lever} ({bps(Math.min(...xs))} to {bps(Math.max(...xs))}) and tenor, the other terms held as asked.
      {lever === "commission" ? " This is a guarantee or letter of credit, so its price is the commission, not a margin." : null}</p>}
    formulas={[
      <>Each cell: the full engine re-run at that {lever} and tenor, RAROC = PV risk-adjusted profit ÷ PV capital.</>,
      <>The dashed line: where RAROC equals the {rate(grid.hurdle)} hurdle (iso-RAROC).</>,
      <>The cross: the ask, {bps(askX)} for {ask.tenor_years} years. The star: the recommendation, once optimised.</>,
    ]}
    read={<p>Green cells clear the hurdle, red cells do not. Cells to the right of the dashed line are acceptable; the closer the cross sits to the line, the thinner the deal.</p>}
    act={<p>If the cross is in red, the shortest step to the dashed line is the cheapest fix: a few bps more {lever}, or a shorter tenor, whichever the client will accept.</p>} />;
}

export function AmountInfo({ grid, ask, ccy }: { grid: Grid; ask: Terms; ccy: string }) {
  return <Explainer testId="dealdesk-info-amount"
    shows={<p>Lifetime RAROC as the amount moves from {ccy} {Math.min(...gridX(grid)).toFixed(0)}m to {Math.max(...gridX(grid)).toFixed(0)}m, the other terms as asked.</p>}
    formulas={[
      <>Each point: the engine re-run at that amount; RAROC = PV risk-adjusted profit ÷ PV capital.</>,
      <>Fixed costs (origination, monitoring) are spread over more balance as the amount grows; collateral covers less of a larger amount, so LGD rises.</>,
      <>Dashed line: the {rate(grid.hurdle)} hurdle; dotted line: the ask, {ccy} {ask.amount}m.</>,
    ]}
    read={<p>A rising line means scale helps (fixed costs dominate); a falling line means security is being diluted.</p>}
    act={<p>If RAROC clears the hurdle only below the ask, offer the lower amount or bring more security for the excess.</p>} />;
}

export function TornadoInfo({ t }: { t: Tornado }) {
  const top = t.bars[0];
  return <Explainer testId="dealdesk-info-tornado"
    shows={<p>How much each lever moves lifetime RAROC from {rate(t.base_raroc)} when moved one step either way, the others held.</p>}
    formulas={[
      <>Bar length = RAROC with the lever moved − {rate(t.base_raroc)}.</>,
      ...(top ? [<>Largest here: {top.lever}, from {rate(top.low)} to {rate(top.high)}.</>] : []),
      <>Green: the step that raises RAROC; red: the step that lowers it.</>,
    ]}
    read={<p>Levers are sorted with the most powerful at the top. A short bar means that lever barely matters for this deal.</p>}
    act={<p>Negotiate on the top two levers first; do not spend client goodwill on levers with short bars.</p>} />;
}

/** Share of the limit used after the deal: value ÷ limit, or limit ÷ value for a minimum (DSCR). */
export function usedShare(c: Constraint): number | null {
  if (typeof c.value !== "number" || typeof c.limit !== "number" || !c.limit) return null;
  if (c.name === "dscr") return c.value > 0 ? c.limit / c.value : 2;
  return c.value / c.limit;
}

export function headroomWords(c: Constraint): string {
  const u = usedShare(c);
  if (u === null) return `${c.label}: ${constraintRead(c)}`;
  const head = Math.round((1 - u) * 100);
  if (c.name === "dscr") return `${c.label}: ${constraintRead(c)} vs minimum ${constraintRead(c, c.limit)}, ${head >= 0 ? `${head}% headroom` : `${-head}% short`}`;
  return `${c.label}: ${constraintRead(c)} of ${constraintRead(c, c.limit)} used, ${head >= 0 ? `${head}% headroom` : `${-head}% over the limit`}`;
}

export function HeadroomInfo({ rows }: { rows: Constraint[] }) {
  const sorted = rows.map((c) => ({ c, u: usedShare(c) })).filter((x) => x.u !== null).sort((a, b) => (b.u as number) - (a.u as number));
  const tight = sorted[0];
  return <Explainer testId="dealdesk-info-headroom"
    shows={<p>Every limit the deal is tested against, measured on the corporate book after the deal, as the share of the limit used.</p>}
    formulas={[
      <>Used = value after the deal ÷ limit (for a minimum such as DSCR: minimum ÷ value). Headroom = 100% − used.</>,
      <>Book limits (single obligor, group, sector) add the deal&apos;s year-1 EAD to the 2026Q2 exposure.</>,
      ...(tight ? [<>Tightest here: {headroomWords(tight.c)}.</>] : []),
    ]}
    read={<p>Bars are sorted, tightest at the top. Green: under 85% used. Amber: 85–100% used, near the limit. Red: over the limit, a breach. The dashed line is the limit itself.</p>}
    act={<p>A red hard limit must be cured (smaller amount, a sell-down, or a different structure) before the deal can be approved. Amber or soft breaches go up the approval chain with a rationale.</p>} />;
}

export function RatingInfo({ rows, hurdle }: { rows: { rating: string; raroc: number }[]; hurdle: number }) {
  return <Explainer testId="dealdesk-info-rating"
    shows={<p>Lifetime RAROC at the current terms with the obligor at its grade ({rows[0]?.rating}) and one and two notches lower.</p>}
    formulas={[
      <>Each bar: the engine re-run with the master-scale PD of that grade; lower grades raise EL and capital.</>,
      ...rows.map((r) => <>{r.rating}: {rate(r.raroc)} against the {rate(hurdle)} hurdle.</>),
    ]}
    read={<p>The faster the bars fall, the more the deal depends on the rating holding. Bars under the dashed line no longer pay for their capital.</p>}
    act={<p>If one notch takes the deal below the hurdle, ask for covenants that trigger repricing on a downgrade, or for security.</p>} />;
}

export function FrontierInfo({ opt }: { opt: OptimizeResult }) {
  const a = opt.frontier[0]; const b = opt.frontier[opt.frontier.length - 1];
  return <Explainer testId="dealdesk-info-frontier"
    shows={<p>The best structures the optimiser found: how far each moves from the client&apos;s ask, against the value it creates.</p>}
    formulas={[
      <>Distance: the weighted sum of how far each term moves from the ask (margin, tenor, amount, security…).</>,
      <>SVA = PV(risk-adjusted profit − hurdle × capital).</>,
      ...(a ? [<>Closest: distance {a.distance.toFixed(2)}, SVA {money(a.sva)}, RAROC {rate(a.lifetime_raroc)}.</>] : []),
      ...(b && b !== a ? [<>Max SVA: distance {b.distance.toFixed(2)}, SVA {money(b.sva)}, RAROC {rate(b.lifetime_raroc)}.</>] : []),
    ]}
    read={<p>Left is easier to sell to the client; up is better for the bank. Every point on the line is the best value for its distance.</p>}
    act={<p>Lead with the closest structure; keep a point further right as the fallback if the client asks for something in return.</p>} />;
}

export function StressInfo({ s }: { s: StressResult }) {
  const worst = [...s.rows].sort((x, y) => x.lifetime_raroc - y.lifetime_raroc)[0];
  return <Explainer testId="dealdesk-info-stress"
    shows={<p>The recommended structure re-run under each stress: downgrades, higher PD and LGD, rates, collateral haircuts.</p>}
    formulas={[
      <>Base: RAROC {rate(s.base.lifetime_raroc)}, SVA {money(s.base.sva)}.</>,
      ...(worst ? [<>Worst: {worst.label}, RAROC {rate(worst.lifetime_raroc)}, SVA {money(worst.sva)}.</>] : []),
      <>Robustness: the number of downgrade notches before RAROC falls below the hurdle ({s.robustness_notches}).</>,
    ]}
    read={<p>Rows marked Below no longer pay for their capital under that stress. Client DSCR shows whether the borrower still covers its debt service.</p>}
    act={<p>Robust to fewer than two notches: add covenants or security before approval, or price for the stress.</p>} />;
}
