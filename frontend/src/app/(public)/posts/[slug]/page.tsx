import Link from "next/link";

import { Markdown } from "@/components/post/Markdown";
import PrevNext from "@/components/post/PrevNext";
import TagList from "@/components/post/TagList";
import Toc from "@/components/post/Toc";
import { serverFetch } from "@/lib/server-api";
import type { NeighborsResponse, PostDetail } from "@/lib/types";

/** 文章详情页（FR-VIEW-08~12）。 */
export default async function PostDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [post, neighbors] = await Promise.all([
    serverFetch<PostDetail>(`/api/posts/${slug}`),
    serverFetch<NeighborsResponse>(`/api/posts/${slug}/neighbors`),
  ]);

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-4xl">
        <header className="mb-8 space-y-3 border-b border-border pb-6">
          {post.category && (
            <Link
              href={`/posts?category=${post.category.slug}`}
              className="text-sm text-accent hover:opacity-80"
            >
              {post.category.name}
            </Link>
          )}
          <h1 className="text-3xl font-semibold leading-tight">{post.title}</h1>
          {post.summary && <p className="text-muted">{post.summary}</p>}
          <div className="flex flex-wrap items-center gap-x-3 text-xs text-faint">
            {post.published_at && (
              <span>发布于 {new Date(post.published_at).toLocaleDateString("zh-CN")}</span>
            )}
            {post.updated_at && post.updated_at !== post.published_at && (
              <span>更新于 {new Date(post.updated_at).toLocaleDateString("zh-CN")}</span>
            )}
            <span>阅读约 {post.read_minutes} 分钟</span>
          </div>
          <TagList tags={post.tags} />
        </header>

        <div className="flex gap-8">
          <article className="min-w-0 flex-1">
            <Markdown content={post.content_md} />
          </article>
          <aside className="hidden w-56 shrink-0 lg:block">
            <div className="sticky top-8 max-h-[calc(100vh-4rem)] overflow-y-auto">
              <Toc items={post.toc} />
            </div>
          </aside>
        </div>

        <PrevNext prev={neighbors.prev} next={neighbors.next} />
      </div>
    </main>
  );
}
