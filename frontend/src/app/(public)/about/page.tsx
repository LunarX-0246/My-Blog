import { Markdown } from "@/components/post/Markdown";
import { serverFetch } from "@/lib/server-api";
import type { PostDetail } from "@/lib/types";

/** 「关于」页保留的文章 slug。博主新建一篇 slug 为 about 的文章即可接管本页内容。 */
const ABOUT_SLUG = "about";

/**
 * 关于页（FR-VIEW-23 / FR-VIEW-24）。
 *
 * FR-VIEW-24 要求内容由博主自己维护、且不再单开一套编辑界面，
 * 所以这里不写死正文，而是去读 slug 为 `about` 的那篇文章 ——
 * 博主在已有的文章编辑器里改，改完就是关于页，不用碰代码。
 * 这篇文章还没建时，退回到一段引导文案，而不是白屏。
 */
export default async function AboutPage() {
  let post: PostDetail | null = null;
  try {
    post = await serverFetch<PostDetail>(`/api/posts/${ABOUT_SLUG}`);
  } catch {
    post = null; // 未创建或未发布，走下面的引导分支
  }

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-3xl space-y-6">
        <h1 className="text-2xl font-semibold">{post?.title ?? "关于"}</h1>
        {post ? (
          <Markdown content={post.content_md} />
        ) : (
          <div className="space-y-3 text-muted">
            <p>本页内容由一篇保留文章提供，目前还没有创建。</p>
            <p className="text-sm text-faint">
              在管理端新建一篇文章，把 slug 设为 <code className="text-accent">about</code>{" "}
              并发布，正文就会显示在这里。
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
