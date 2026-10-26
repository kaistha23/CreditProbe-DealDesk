import { InvestigationDetail } from "@/components/v5/workspace/investigations";

/** One investigation. Back goes to Investigations. */
export default async function InvestigationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <InvestigationDetail id={decodeURIComponent(id)} />;
}
