"use client";

/**
 * Committee-pack playbooks (PLAN_R9 D4): ECL committee, watchlist committee, Accepted Risk Watch quarterly review,
 * auditor query response and credit review opinion. Each shows its steps, the data it reads and its output; "Run"
 * produces the Word document from the books and the CBUAE CRM checks now.
 */

import * as React from "react";
import { ChevronRight, FileDown, Loader2 } from "lucide-react";

import { SectionTitle } from "@/components/v5/workspace/parts";
import { playbookOrigin } from "@/lib/v5/playbook";

interface CommitteePlaybook { id: string; name: string; audience: string; frequency: string; steps: string[]; data: string[]; output: string }

const base = () => `${playbookOrigin()}/api/v1/playbook/committee`;

export function CommitteePlaybooks() {
  const [items, setItems] = React.useState<CommitteePlaybook[] | null>(null);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState("");
  const [done, setDone] = React.useState<Record<string, string>>({});
  const [open, setOpen] = React.useState("");

  React.useEffect(() => {
    fetch(base(), { credentials: "include", cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => setItems(d.playbooks)).catch(() => setError("The committee playbooks are temporarily unavailable."));
  }, []);

  const run = async (p: CommitteePlaybook) => {
    if (busy) return;
    setBusy(p.id); setError("");
    try {
      const r = await fetch(`${base()}/${p.id}/run`, { method: "POST", credentials: "include", cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      const blob = await r.blob();
      const cd = r.headers.get("Content-Disposition") ?? "";
      const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? `${p.name}.docx`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      setDone((d) => ({ ...d, [p.id]: name }));
    } catch { setError(`${p.name} could not be produced. Please try again.`); }
    finally { setBusy(""); }
  };

  if (!items && !error) return null;
  // R10 C2: one compact row each (name · committee · cadence · Run); the steps open behind a click.
  return (
    <section data-testid="playbook-committee">
      <SectionTitle>Committee playbooks</SectionTitle>
      {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
      <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
        {(items ?? []).map((p) => (
          <li key={p.id} data-testid={`committee-${p.id}`}>
            <div className="flex items-center gap-2 px-3 py-2">
              <button type="button" onClick={() => setOpen(open === p.id ? "" : p.id)} aria-expanded={open === p.id}
                      data-testid={`committee-${p.id}-details`} title={open === p.id ? "Hide steps" : `${p.steps.length} steps · data · output`}
                      className="flex min-w-0 flex-1 items-center gap-1.5 text-left">
                <ChevronRight size={14} className={`shrink-0 text-text-muted transition-transform ${open === p.id ? "rotate-90" : ""}`} aria-hidden />
                <span className="truncate text-[13px] font-medium text-text-primary">{p.name}</span>
                <span className="hidden truncate text-[11px] text-text-muted sm:inline">· {p.audience} · {p.frequency}</span>
              </button>
              {done[p.id] ? <span className="hidden max-w-[160px] truncate text-[11px] text-positive md:inline" data-testid={`committee-${p.id}-done`}
                                  title={`Word ready: ${done[p.id]}`}>Word ready</span> : null}
              <button type="button" onClick={() => void run(p)} disabled={Boolean(busy)} data-testid={`committee-${p.id}-run`}
                      aria-label={`Run ${p.name}`}
                      className="inline-flex shrink-0 items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[12px] font-medium text-text-primary hover:border-accent hover:text-accent disabled:opacity-50">
                {busy === p.id ? <Loader2 size={12} className="animate-spin" /> : <FileDown size={12} />} Run</button>
            </div>
            {open === p.id ? (
              <div className="space-y-1.5 border-t border-border bg-surface-sunken px-3 py-2 text-[12px]">
                <ol className="list-decimal space-y-0.5 pl-4 text-text-secondary">{p.steps.map((s) => <li key={s}>{s}</li>)}</ol>
                <p className="text-text-muted"><b className="text-text-secondary">Data:</b> {p.data.join("; ")}</p>
                <p className="text-text-muted"><b className="text-text-secondary">Output:</b> {p.output}</p>
              </div>) : null}
          </li>))}
      </ul>
    </section>
  );
}
