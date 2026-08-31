import Link from "next/link";

import { serverFetch } from "@/lib/server-api";
import type { PostListResponse, TagOut } from "@/lib/types";

/** 标签页（FR-VIEW-07）：某标签下的全部文章（文档在阶段 2 一并展示）。 */
export default async function TagPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [data, tags] = await Promise.all([
    serverFetch<PostListResponse>(`/api/posts?tag=${slug}`),
    serverFetch<TagOut[]>("/api/tags"),
  ]);
  const tagName = tags.find((t) => t.slug === slug)?.name ?? slug;

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-3xl">
        <h1 className="mb-6 text-2xl font-semibold">标签：{tagName}</h1>
        {data.items.length === 0 ? (
          <p className="text-muted">该标签下暂无内容。</p>
        ) : (
          <ul className="space-y-6">
            {data.items.map((p) => (
              <li key={p.id} className="space-y-1">
                <Link href={`/posts/${p.slug}`} className="text-lg font-medium hover:text-accent">
                  {p.title}
                </Link>
                {p.summary && <p className="text-sm text-muted">{p.summary}</p>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
