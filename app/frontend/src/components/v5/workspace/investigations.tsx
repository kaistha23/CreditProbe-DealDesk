"use client";

/**
 * Investigations: one question worked through over time -- the figures it
 * rests on (quoted from the v5 book), a timeline of notes and status changes,
 * the saved analyses behind it, and links into the live modules.
 */

import Link from "next/link";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { cn } from "@/lib/utils";
import { type InvestigationDetail as Detail, formatValue, useWs, when, words, ws } from "@/lib/v5/workspace";
import { ShareButton } from "@/components/v5/mail/share";
import { AddToReportButton, type BuiltSection } from "@/components/v5/playbook/add-to-report";
import { Conversation } from "@/components/v5/workspace/conversation";
import { ws3, type Source, type Turn } from "@/lib/v5/workspace-r3";
import { ArrowUpRight } from "lucide-react";

import { Empty, ErrorBox, LinkChips, Loading, PageTop, Prose, SectionTitle, StatusPill, Who, inputClass, useViewer } from "./parts";
import { Related } from "./projects";
import { edition } from "@/lib/navigation";

export function InvestigationList() {
  const list = useWs(() => ws.investigations(), "investigations");
  return (
    <div className="space-y-5" data-testid="ws-investigations">
      <PageTop title="Investigations"
               about="A question worked through over time: the figures it rests on, the notes and decisions along the way, and the analyses kept as evidence." />
      {list.error ? <ErrorBox error={list.error} /> : !list.data ? <Loading /> : list.data.investigations.length === 0 ? <Empty>No investigations yet.</Empty> : (
        <div className="space-y-3">
          {list.data.investigations.map((i) => (
            <Card key={i.id} className="p-0" data-testid={`ws-investigation-${i.id}`}>
              <Link href={`/investigations/${i.id}`} className="block space-y-2 p-4 transition-colors hover:bg-surface-hover">
                <div className="flex flex-wrap items-start gap-2">
                  <h3 className="min-w-0 flex-1 text-[15px] font-semibold text-text-primary">{i.title}</h3>
                  <StatusPill status={i.status} />
                </div>
                <p className="text-sm text-text-secondary">{i.summary}</p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
                  {i.figures.slice(0, 4).map((f) => (
                    <div key={f.key}>
                      <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-text-muted">{f.label} · {f.period}</p>
                      <p className="text-[13px] font-medium tabular-nums">{formatValue(f.value, f.unit)}</p>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-text-muted">
                  {(i as typeof i & { source?: Partial<Source> }).source?.label ? `From ${(i as typeof i & { source?: Partial<Source> }).source?.label} · ` : ""}
                  {(i as typeof i & { turn_count?: number }).turn_count ? `${(i as typeof i & { turn_count?: number }).turn_count} turns · ` : ""}
                  {i.sector ? `${i.sector} · ` : ""}{i.owner ? `Owner ${i.owner.name}` : ""} · {i.notes} notes · updated {when(i.updated_at)}
                </p>
              </Link>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export function InvestigationDetail({ id }: { id: string }) {
  const viewer = useViewer();
  const [fresh, setFresh] = React.useState<Detail | null>(null);
  const loaded = useWs(() => ws.investigation(id), `investigation|${id}`);
  const inv = fresh && fresh.id === id ? fresh : loaded.data;
  const back = { href: "/investigations", label: "Investigations" };
  if (loaded.error) return <div className="space-y-4"><PageTop title="Investigation" back={back} /><ErrorBox error={loaded.error} /></div>;
  if (!inv) return <div className="space-y-4"><PageTop title="Investigation" back={back} /><Loading /></div>;

  const x = inv as Detail & { turns?: Turn[]; source?: Partial<Source>; continue_href?: string };
  const object = { type: "investigation" as const, id: inv.id, label: `Investigation: ${inv.title}`,
                   href: `/investigations/${inv.id}`, summary: inv.summary.slice(0, 300) };
  return (
    <div className="space-y-5" data-testid={`ws-investigation-detail-${inv.id}`}>
      <PageTop eyebrow="Investigation" title={inv.title} back={back} subtitle={inv.summary}
               actions={<>
                 {x.continue_href ? (
                   <Button asChild size="sm"><Link href={x.continue_href} data-testid="ws-investigation-continue">Continue in {x.source?.label?.split(" · ")[0] || "the source"} <ArrowUpRight aria-hidden /></Link></Button>
                 ) : null}
                 <ShareButton object={object} testId="ws-investigation-share" />
                 <AddToReportButton source={object} testId="ws-investigation-add-report" defaultTitle={inv.title}
                                    build={async () => (await ws3.investigationSection(inv.id)).section as unknown as BuiltSection} />
               </>} />
      <div className="flex flex-wrap items-center gap-3 text-xs text-text-secondary">
        <StatusPill status={inv.status} testId="ws-investigation-status" />
        {x.source?.href ? <Link href={x.source.href} className="text-accent hover:underline" data-testid="ws-investigation-source">From {x.source.label}</Link> : null}
        {inv.owner ? <span>Owner <Who person={inv.owner} /></span> : null}
        {inv.sector ? <span>Sector {inv.sector}</span> : null}
        {inv.period ? <span>{inv.compare_period} → {inv.period}</span> : null}
        {inv.project ? <Link className="text-accent hover:underline" href={`/projects/${inv.project.id}`}>Project · {inv.project.name}</Link> : null}
      </div>

      {inv.figures.length ? <section>
        <SectionTitle>Figures from the book</SectionTitle>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="ws-investigation-figures">
          {inv.figures.map((f) => (
            <Card key={f.key} className="p-3" data-testid={`ws-figure-${f.key}`} title={`Source: ${f.source}`}>
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">{f.label}</p>
              <p className="mt-0.5 text-lg font-semibold tabular-nums">{formatValue(f.value, f.unit)}</p>
              <p className="text-[11px] text-text-muted">{f.period}</p>
            </Card>
          ))}
        </div>
        <div className="mt-2 flex justify-end"><InfoPopover title="Source">{edition() === "dealdesk" ? "The corporate credit book (20 quarters). SAR million." : "The corporate book (Early Warning release ews-saudi-corporate-20q-v4e2). SAR million."}</InfoPopover></div>
      </section> : null}

      {x.turns?.length ? (
        <section>
          <SectionTitle>The conversation · {x.turns.length} turns</SectionTitle>
          <Conversation turns={x.turns} />
          <ContinueHere id={inv.id} onSaved={setFresh} />
        </section>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <section>
          <SectionTitle>Timeline</SectionTitle>
          <ol className="space-y-2">
            {inv.timeline.map((n) => (
              <li key={n.id} data-testid={`ws-note-${n.id}`}
                  className={cn("rounded-lg border p-3.5", n.kind === "status" ? "border-dashed border-border bg-surface-sunken" : "border-border bg-surface")}>
                <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2 text-xs">
                  <Who person={n.author} />
                  <span className="flex items-center gap-2 text-text-muted">
                    {n.kind === "status" ? "Status change · " : ""}{when(n.created_at)}
                  </span>
                </div>
                <Prose text={n.body} />
              </li>
            ))}
          </ol>
          <AddNote id={id} viewer={viewer} status={inv.status} statuses={inv.statuses} onSaved={setFresh} />
        </section>
        <aside className="space-y-5">
          <section>
            <SectionTitle>Open in the modules</SectionTitle>
            <LinkChips links={inv.links} />
          </section>
          <Related title="Saved analyses" items={inv.analyses.map((a) => ({ href: `/analyses/${a.id}`, label: a.title }))} />
        </aside>
      </div>
    </div>
  );
}

function AddNote({ id, viewer, status, statuses, onSaved }: {
  id: string; viewer: string; status: string; statuses: string[]; onSaved: (d: Detail) => void;
}) {
  const [body, setBody] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  async function run(fn: () => Promise<Detail>) {
    setBusy(true);
    setError(null);
    try {
      onSaved(await fn());
      setBody("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card className="mt-3 space-y-2 p-3">
      <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} placeholder="Add a note…" aria-label="New note"
                className={cn(inputClass, "resize-y")} data-testid="ws-note" />
      {error ? <p className="text-xs text-negative" role="alert">{error}</p> : null}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-xs text-text-secondary">
          Status
          <select value={status} disabled={busy} data-testid="ws-investigation-status-select"
                  onChange={(e) => void run(() => ws.investigationStatus(id, e.target.value, body.trim()))}
                  className="rounded-md border border-border bg-surface px-2 py-1 text-xs">
            {statuses.map((s) => <option key={s} value={s}>{words(s)}</option>)}
          </select>
        </label>
        <Button size="sm" onClick={() => void run(() => ws.addNote(id, body))} disabled={busy || !body.trim()}
                data-testid="ws-note-send">
          Add note
        </Button>
      </div>
    </Card>
  );
}


/** Continue the investigation here: a turn added to its conversation (the source thread opens with Continue). */
function ContinueHere({ id, onSaved }: { id: string; onSaved: (d: Detail) => void }) {
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  async function send() {
    setBusy(true);
    setError(null);
    try {
      await ws3.addTurns(id, [{ role: "note", text }]);
      onSaved(await ws.investigation(id));
      setText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add it.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card className="mt-3 space-y-2 p-3">
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} aria-label="Continue the conversation"
                placeholder="Add a finding or the next question…"
                className={cn(inputClass, "resize-y")} data-testid="ws-turn-input" />
      {error ? <p className="text-xs text-negative" role="alert">{error}</p> : null}
      <div className="flex justify-end">
        <Button size="sm" onClick={() => void send()} disabled={busy || !text.trim()} data-testid="ws-turn-send">Add to the conversation</Button>
      </div>
    </Card>
  );
}
