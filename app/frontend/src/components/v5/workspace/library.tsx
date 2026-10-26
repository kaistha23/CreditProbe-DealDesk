"use client";

/**
 * Saved analyses (a figure table kept with its period, source and notes) and
 * Documents (committee pack drafts and credit memos, text only).
 */

import Link from "next/link";
import * as React from "react";
import { FileText } from "lucide-react";

import { Card } from "@/components/ui/card";
import { day, useWs, when, ws } from "@/lib/v5/workspace";

import { Empty, ErrorBox, LinkChips, Loading, PageTop, Prose, SectionTitle, StatusPill, Who } from "./parts";

// Analyses moved to ./analyses.tsx (S3-2: refresh, before/after).

// --------------------------------------------------------------- documents

export function DocumentList() {
  const list = useWs(() => ws.documents(), "documents");
  return (
    <div className="space-y-5" data-testid="ws-documents">
      <PageTop title="Documents"
               about="Committee papers and credit memos written from the workspace, quoting the v5 book. Text only." />
      {list.error ? <ErrorBox error={list.error} /> : !list.data ? <Loading /> : list.data.documents.length === 0 ? <Empty>No documents yet.</Empty> : (
        <div className="grid gap-3 md:grid-cols-2">
          {list.data.documents.map((d) => (
            <Card key={d.id} className="p-0" data-testid={`ws-document-${d.id}`}>
              <Link href={`/documents/${d.id}`} className="flex gap-3 p-4 transition-colors hover:bg-surface-hover">
                <FileText className="mt-0.5 size-4 shrink-0 text-text-muted" aria-hidden />
                <span className="min-w-0 flex-1 space-y-1">
                  <span className="flex items-start gap-2">
                    <span className="min-w-0 flex-1 text-[15px] font-semibold text-text-primary">{d.title}</span>
                    <StatusPill status={d.status} />
                  </span>
                  <span className="block text-sm text-text-secondary">{d.summary}</span>
                  <span className="block text-xs text-text-muted">
                    {d.kind} · {d.section_count} sections · {d.words} words · {d.owner ? d.owner.name : ""} · updated {day(d.updated_at)}
                  </span>
                </span>
              </Link>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export function DocumentDetail({ id }: { id: string }) {
  const doc = useWs(() => ws.document(id), `document|${id}`);
  const back = { href: "/documents", label: "Documents" };
  if (doc.error) return <div className="space-y-4"><PageTop title="Document" back={back} /><ErrorBox error={doc.error} /></div>;
  if (!doc.data) return <div className="space-y-4"><PageTop title="Document" back={back} /><Loading /></div>;
  const d = doc.data;
  return (
    <div className="space-y-5" data-testid={`ws-document-detail-${d.id}`}>
      <PageTop eyebrow={d.kind} title={d.title} back={back} subtitle={d.summary} />
      <div className="flex flex-wrap items-center gap-3 text-xs text-text-secondary">
        <StatusPill status={d.status} />
        {d.owner ? <span>Author <Who person={d.owner} /></span> : null}
        <span>Updated {when(d.updated_at)}</span>
        {d.project_id ? <Link className="text-accent hover:underline" href={`/projects/${d.project_id}`}>Project</Link> : null}
      </div>
      <div className="grid gap-5 lg:grid-cols-[3fr_1fr]">
        <Card className="space-y-6 p-6" data-testid="ws-document-body">
          {d.sections.map((s, i) => (
            <section key={i}>
              <h2 className="mb-2 text-[15px] font-semibold text-text-primary">{s.heading}</h2>
              <Prose text={s.body} />
            </section>
          ))}
        </Card>
        <aside className="space-y-3">
          <SectionTitle>Linked</SectionTitle>
          <LinkChips links={d.links} className="flex-col items-start" />
        </aside>
      </div>
    </div>
  );
}
