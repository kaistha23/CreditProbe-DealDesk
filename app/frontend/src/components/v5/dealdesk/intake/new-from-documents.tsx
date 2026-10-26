"use client";

/**
 * R16 i: New proposal → "Customer documents" (the first tab). Upload the customer's documents, see the customer file,
 * then open the deal: an existing customer's deal in Data Domains when the CR number matches (the bank data joins),
 * else a new proposal prefilled from the documents (name, CR, sector, revenue, EBITDA, debt, the ask). The file is
 * attached to the deal, so the business request, the credit response and the deal's More → Customer file read it.
 *
 * Round A: the first screen is the agent (agent-intake.tsx): the RM drops the pack with the ask and the notes and the agent
 * reads, checks and drafts the business request. Its pack is this customer file; the open / create actions and the R16 file
 * view follow the run, unchanged.
 */

import * as React from "react";
import { ArrowRight } from "lucide-react";

import { PlainWords } from "@/components/v5/ui/plain-words";
import { dealdesk } from "@/lib/v5/dealdesk";
import { type CustomerFile, intake, prefillFromFacts } from "@/lib/v5/dealdesk-intake";
import { friendlyMessage } from "@/lib/v5/errors";

import { PrimaryButton, SecondaryButton } from "../kit";
import { agentIntake, type AgentRun } from "@/lib/v5/dealdesk-agent-intake";

import { AgentIntake } from "./agent-intake";
import { CustomerFileView } from "./customer-file";

export function NewFromDocuments({ base, sectors, onCreated }: {
  /** the short form's default values (every field the create call needs) */
  base: Record<string, string>; sectors: string[]; onCreated: (id: string) => void;
}) {
  const [file, setFile] = React.useState<CustomerFile | null>(null);
  const [run, setRun] = React.useState<AgentRun | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  const onRun = async (r: AgentRun) => {
    setRun(r);
    if (!r.intake_id) return;
    try { setFile(await intake.get(r.intake_id)); } catch (e) { setError(friendlyMessage(e)); }
  };
  const linkRun = async (pid: string) => { if (run) await agentIntake.attach(run.run_id, pid).catch(() => undefined); };
  const existingPid = file?.bank.existing ? file.bank.proposal_id ?? "" : "";
  const openExisting = async () => {
    if (!file || !existingPid) return;
    setBusy(true); setError("");
    try { await intake.attach(file.intake_id, existingPid); await linkRun(existingPid); onCreated(existingPid); } catch (e) { setError(friendlyMessage(e)); setBusy(false); }
  };
  const createNew = async () => {
    if (!file) return;
    setBusy(true); setError("");
    try {
      const f = await intake.facts(file.intake_id);
      const values = { ...base, ...prefillFromFacts(f, sectors) };
      if (!values.name?.trim()) values.name = file.profile.customer_name || "New customer";
      const p = await dealdesk.createFromFields(values, { form: true, intake_id: file.intake_id, filename: `${file.documents_n} customer documents` });
      await intake.attach(file.intake_id, p.proposal_id);
      await linkRun(p.proposal_id);
      onCreated(p.proposal_id);
    } catch (e) { setError(friendlyMessage(e)); setBusy(false); }
  };

  const actions = !file ? null : (
    <div className="flex flex-wrap items-center justify-end gap-2" data-testid="intake-actions">
      {error ? <p className="mr-auto text-[12px] text-negative" role="alert">{error}</p> : null}
      {existingPid ? <SecondaryButton onClick={() => void createNew()} disabled={busy} data-testid="intake-create-new">New proposal instead</SecondaryButton> : null}
      {existingPid
        ? <PrimaryButton onClick={() => void openExisting()} disabled={busy} data-testid="intake-open-deal">
            Open {file.bank.name || file.profile.customer_name}&apos;s deal ({existingPid}) with this file <ArrowRight size={14} /></PrimaryButton>
        : <PrimaryButton onClick={() => void createNew()} disabled={busy} data-testid="intake-create">
            Create the proposal from this file <ArrowRight size={14} /></PrimaryButton>}
    </div>);
  return (
    <div data-testid="intake-new">
      <AgentIntake onRun={(r) => void onRun(r)} footer={file ? (
        <div className="space-y-3 border-t border-border pt-4" data-testid="agent-customer-file">
          <PlainWords testId="intake-new-plain" lines={[
            "The pack is the customer file: what each document is, the required list, and whether the numbers agree.",
            "If the customer already banks with us, it pulls their accounts, facilities and group.",
            "Open or create the deal from it: the file and the request go with the deal.",
          ]} />
          <CustomerFileView file={file} onChange={setFile} footer={actions} />
        </div>) : error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null} />
    </div>);
}
