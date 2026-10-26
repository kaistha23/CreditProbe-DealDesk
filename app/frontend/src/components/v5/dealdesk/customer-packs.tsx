"use client";

/**
 * R16 d: Deal Desk → Customer packs. The four customers' files (Word, PDF, photos) with the document checklist, what to
 * type (the ask and the RM notes), and, for existing customers, the Bank's own file (accounts, limits, group) traced to
 * Data Domains. Reached from the proposal list (the "Customer packs" link under the table).
 */

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Check, Copy, Download, FileText, Image as ImageIcon, Users } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { BackLink, pushFrom } from "@/components/v5/ui/back-link";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import { type BankFile, type PackDetail, type PackSummary, checklist, dmy, fileHref, mn, packLine, packsApi } from "@/lib/v5/dealdesk-packs";

import { b360Href } from "@/components/v5/ui/borrower-360-model";

import { CustomerBorrower360 } from "./b360"; // Round B: a borrower link (?cif=) lands on the customer's 360
import { InfoPopover } from "./explain";
import { Chip, Section, SecondaryButton, tableCls, tdCls, thCls } from "./kit";

const TONE = { received: "positive", expired: "warning", missing: "negative" } as const;

function CopyLine({ label, text, testId }: { label: string; text: string; testId: string }) {
  const [done, setDone] = React.useState(false);
  if (!text) return null;
  const copy = () => {
    void navigator.clipboard?.writeText(text).then(() => { setDone(true); window.setTimeout(() => setDone(false), 1500); }).catch(() => undefined);
  };
  return (
    <div className="space-y-1" data-testid={testId}>
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">{label}</span>
        <button type="button" onClick={copy} aria-label={`Copy ${label.toLowerCase()}`} data-testid={`${testId}-copy`}
                className="inline-flex h-6 items-center gap-1 rounded border border-border px-2 text-[11px] text-text-secondary hover:bg-surface-hover">
          {done ? <Check size={12} /> : <Copy size={12} />}{done ? "Copied" : "Copy"}</button>
      </div>
      <p className="rounded-md border border-border bg-surface-muted/40 px-3 py-2 text-[13px] text-text-primary">{text}</p>
    </div>
  );
}

function Files({ k, files }: { k: string; files: { docx: string; pdf: string; images: string[] } | null }) {
  if (!files) return <span className="text-text-muted">–</span>;
  const a = "inline-flex items-center gap-1 text-accent hover:underline";
  return (
    <span className="inline-flex flex-wrap items-center gap-3">
      <a className={a} href={fileHref(k, files.docx)} download><FileText size={12} />Word</a>
      <a className={a} href={fileHref(k, files.pdf)} download><Download size={12} />PDF</a>
      {files.images.map((im, i) => <a key={im} className={a} href={fileHref(k, im)} download><ImageIcon size={12} />Photo{files.images.length > 1 ? ` ${i + 1}` : ""}</a>)}
    </span>
  );
}

function BankPanel({ bank }: { bank: BankFile }) {
  const router = useRouter();
  if (!bank.existing || !bank.summary) return <PlainWords lines={bank.plain_words} testId="packs-bank-words" />;
  const s = bank.summary;
  return (
    <Section title="The Bank's file" testId="packs-bank"
             info="What the Bank already holds on this customer, from Data Domains (customer accounts, account conduct, facility limits, group entities). Each row traces to its relation.">
      <PlainWords lines={bank.plain_words} testId="packs-bank-words" />
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="packs-bank-tiles">
        {[["Balances", mn(s.balances_mn)], ["Credit turnover, 12 months", mn(s.credit_turnover_12m_mn)], ["Limits / used", `${mn(s.limits_mn)} / ${mn(s.outstanding_mn)}`],
          ["Average utilisation", `${s.avg_utilisation_12m_pct.toFixed(0)}%`]].map(([l, v]) => (
          <div key={l} className="rounded-md border border-border px-3 py-2"><p className="text-[11px] text-text-muted">{l}</p><p className="text-[15px] font-semibold tabular-nums">{v}</p></div>))}
      </div>
      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        <table className={tableCls} data-testid="packs-bank-accounts">
          <thead><tr><th className={thCls}>Account</th><th className={thCls}>Holder</th><th className={cn(thCls, "text-right")}>Balance</th><th className={cn(thCls, "text-right")}>Credits, 12m</th></tr></thead>
          <tbody>{(bank.accounts ?? []).map((a) => (
            <tr key={a.account_no} title={`${a.trace.relation} · ${Object.values(a.trace.key).join(" · ")} · v${a.trace.version}`}>
              <td className={cn(tdCls, "whitespace-normal")}>{a.label}<span className="block text-[11px] text-text-muted">{a.account_no}</span></td>
              <td className={tdCls}>{a.obligor_id}</td><td className={cn(tdCls, "text-right")}>{mn(a.balance_mn, 2)}</td><td className={cn(tdCls, "text-right")}>{mn(a.credits_12m_mn)}</td></tr>))}
          </tbody>
        </table>
        <table className={tableCls} data-testid="packs-bank-group">
          <thead><tr><th className={thCls}>Group entity</th><th className={thCls}>Role</th><th className={thCls}>Status</th></tr></thead>
          <tbody>{(bank.group ?? []).map((g) => (
            <tr key={g.entity_id} title={g.credit_status_note || g.trace.relation}>
              <td className={cn(tdCls, "whitespace-normal")}>{g.entity_name}</td><td className={tdCls}>{g.role}</td>
              <td className={tdCls}><Chip tone={g.credit_status === "performing" ? "positive" : "negative"}>{g.credit_status.replace(/_/g, " ")}</Chip></td></tr>))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {bank.borrower_360 ? <SecondaryButton data-testid="packs-open-b360"
          onClick={() => pushFrom(router, b360Href(bank.borrower_360!.customer_id), "deal-desk")}>
          <Users size={13} /> Open in Borrower 360</SecondaryButton> : null}
        {bank.proposal_id ? <SecondaryButton data-testid="packs-open-deal" onClick={() => pushFrom(router, `/deal-desk/${encodeURIComponent(bank.proposal_id!)}`, "deal-desk")}>
          <FileText size={13} /> Open the customer file on Deal Desk</SecondaryButton> : null}
      </div>
    </Section>
  );
}

export function CustomerPacksPage() {
  const params = useSearchParams();
  const router = useRouter();
  const [list, setList] = React.useState<{ packs: PackSummary[]; plain_words: string[] } | null>(null);
  const [err, setErr] = React.useState("");
  const key = params.get("pack") ?? "";
  const cif = (params.get("cif") ?? "").trim();
  const [detail, setDetail] = React.useState<PackDetail | null>(null);
  const [bank, setBank] = React.useState<BankFile | null>(null);

  React.useEffect(() => { packsApi.list().then(setList).catch((e: Error) => setErr(e.message)); }, []);
  const chosen = key || (cif ? (list?.packs.find((p) => p.cif === cif)?.key ?? "") : (list?.packs[0]?.key ?? ""));
  React.useEffect(() => {
    if (!chosen) return;
    let live = true;
    setDetail(null); setBank(null);
    packsApi.get(chosen).then((d) => { if (live) setDetail(d); }).catch((e: Error) => setErr(e.message));
    packsApi.bank(chosen).then((b) => { if (live) setBank(b); }).catch(() => undefined);
    return () => { live = false; };
  }, [chosen]);
  const pick = (k: string) => router.replace(`/deal-desk/customer-packs?pack=${encodeURIComponent(k)}`, { scroll: false });

  return (
    <div className="space-y-4" data-testid="customer-packs">
      <div className="flex flex-wrap items-center gap-2">
        <BackLink fallback={{ label: "Deal Desk", href: "/deal-desk" }} />
        <h1 className="text-2xl font-semibold text-text-primary">{cif ? "Customer file" : "Customer packs"}</h1>
        {cif ? <a href="/deal-desk/customer-packs" className="text-[12px] text-accent hover:underline" data-testid="packs-all">All customer packs</a> : null}
        <InfoPopover title="Customer packs">
          Four customer files to try Deal Desk end to end: the documents a bank asks for (KYC, company legal, bureau, financials,
          statements and the extras), as Word, PDF and photos of the key pages. All names and figures are fictional.
        </InfoPopover>
      </div>
      {err ? <p className="text-[12px] text-negative" role="alert">{err}</p> : null}
      {cif ? <CustomerBorrower360 cif={cif} /> : null}
      {cif ? null : <PlainWords lines={list?.plain_words ?? []} loading={!list} testId="packs-words" />}
      {cif ? null : !list ? <Skeleton className="h-28 w-full" /> : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" data-testid="packs-cards">
          {list.packs.map((p) => (
            <button key={p.key} type="button" onClick={() => pick(p.key)} data-testid={`packs-card-${p.key}`} aria-pressed={p.key === chosen}
                    className={cn("rounded-lg border p-3 text-left hover:bg-surface-hover", p.key === chosen ? "border-accent bg-accent-muted/40" : "border-border bg-surface")}>
              <div className="flex items-center gap-2"><span className="text-[14px] font-semibold text-text-primary">{p.customer_name}</span></div>
              <p className="mt-1 text-[12px] text-text-secondary">{packLine(p)}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Chip tone={p.existing ? "accent" : "neutral"}>{p.existing ? `Existing · ${p.cif}` : "New to bank"}</Chip>
                <Chip>CR {p.cr_number}</Chip>{p.business_request ? <Chip tone="warning">Business request</Chip> : null}
              </div>
            </button>))}
        </div>)}

      {chosen && !detail ? <Skeleton className="h-64 w-full" /> : null}
      {detail ? (<>
        <Section title={`What to type — ${detail.customer_name}`} testId="packs-ask"
                 info="The ask goes in the Deal Desk chat box after the upload; the RM notes in the RM notes box.">
          <div className="space-y-3">
            <CopyLine label="The ask" text={detail.ask} testId="packs-ask-text" />
            <CopyLine label="RM notes" text={detail.rm_notes} testId="packs-notes-text" />
            {detail.business_request ? (
              <div className="text-[12px]" data-testid="packs-business-request">
                <span className="mr-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">Business request to upload</span>
                <Files k={detail.key} files={detail.business_request} />
              </div>) : null}
          </div>
        </Section>
        {bank ? <BankPanel bank={bank} /> : null}
        <Section title="Document checklist" testId="packs-checklist"
                 info="Status on the demo day: received, expired (past its expiry or older than its validity) or missing (not provided on purpose).">
          <PlainWords lines={detail.plain_words} testId="packs-checklist-words" />
          <div className="mt-3 overflow-auto">
            <table className={tableCls} data-testid="packs-docs">
              <thead><tr><th className={thCls}>Status</th><th className={thCls}>Document</th><th className={thCls}>Issued</th><th className={thCls}>Expires</th><th className={thCls}>Files</th></tr></thead>
              <tbody>{checklist(detail.documents).map((d, i) => (
                <tr key={`${d.doc_type}-${d.subject}-${i}`} data-testid={`packs-doc-${d.status}`}>
                  <td className={tdCls}><Chip tone={TONE[d.status]}>{d.status_label}</Chip></td>
                  <td className={cn(tdCls, "whitespace-normal")}><span className="text-text-primary">{d.label}</span>
                    {d.status !== "missing" && d.title !== d.label ? <span className="block text-[11px] text-text-muted">{d.title}</span> : null}
                    {d.why ? <span className="block text-[11px] text-text-muted">{d.why}</span> : null}</td>
                  <td className={tdCls}>{dmy(d.issue_date)}</td><td className={tdCls}>{dmy(d.expiry_date)}</td>
                  <td className={cn(tdCls, "whitespace-normal")}><Files k={detail.key} files={d.files} /></td>
                </tr>))}
              </tbody>
            </table>
          </div>
        </Section>
      </>) : null}
    </div>
  );
}
