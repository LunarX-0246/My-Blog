import AskPanel from "@/components/ask/AskPanel";

/** 独立全屏问答页（FR-ASK-01）。支持 ?post=slug 限定单篇（FR-ASK-14）。 */
export default async function AiPage({
  searchParams,
}: {
  searchParams: Promise<{ post?: string }>;
}) {
  const { post } = await searchParams;
  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-3xl">
        <h1 className="mb-2 text-2xl font-semibold">AI 问答</h1>
        {post && <p className="mb-6 text-sm text-accent">范围：仅这篇文章</p>}
        <AskPanel scope={post ? { post_slug: post } : undefined} />
      </div>
    </main>
  );
}
