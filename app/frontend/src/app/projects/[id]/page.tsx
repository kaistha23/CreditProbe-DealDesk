import { ProjectDetail } from "@/components/v5/workspace/projects";

/** One project. Back goes to Projects. */
export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProjectDetail id={decodeURIComponent(id)} />;
}
