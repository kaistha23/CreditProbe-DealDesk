import { redirect } from "next/navigation";

/** The old Documents moved into Playbook (PLAN_R3 S1-2): an old document link opens the same document there. */
const MOVED: Record<string, string> = {
  "committee-pack-q2-2026-draft": "rp_committee_pack_q2_2026_draft",
  "credit-memo-cb01045": "rp_memo_cb01045",
};

export default async function DocumentPage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const report = MOVED[decodeURIComponent(id)];
  const embed = sp.embed === "1" ? "&embed=1" : "";
  redirect(report ? `/playbook?report=${report}${embed}` : `/playbook${embed ? "?embed=1" : ""}`);
}
