import { AnalysisDetail } from "@/components/v5/workspace/analyses";

/** One saved analysis and its figure table. Back goes to Analyses. */
export default async function AnalysisPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AnalysisDetail id={decodeURIComponent(id)} />;
}
