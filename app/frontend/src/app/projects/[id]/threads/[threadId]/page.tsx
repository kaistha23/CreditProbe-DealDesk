import { ProjectThreadView } from "@/components/v5/workspace/project-scope";

/** One thread inside a project, answered only from the project's domains, documents and instructions. Back goes to the project. */
export default async function ProjectThreadPage({ params }: { params: Promise<{ id: string; threadId: string }> }) {
  const { id, threadId } = await params;
  return <ProjectThreadView projectId={decodeURIComponent(id)} threadId={decodeURIComponent(threadId)} />;
}
