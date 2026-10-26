import { redirect } from "next/navigation";

/** Old conversation links open the same conversation in Mail. */
export default async function MessageThreadPage({ params }: { params: Promise<{ threadId: string }> }) {
  const { threadId } = await params;
  redirect(`/messages?thread=${encodeURIComponent(decodeURIComponent(threadId))}`);
}
