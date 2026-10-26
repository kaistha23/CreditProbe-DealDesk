import { redirect } from "next/navigation";

/** The old Documents page (PLAN_R3 S1-2): policies and circulars are in Policy Docs; reports and memos in Playbook. */
export default function DocumentsPage() {
  redirect("/policy-docs");
}
