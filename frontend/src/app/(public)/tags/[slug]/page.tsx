import Link from "next/link";

import { serverFetch } from "@/lib/server-api";
import type { DocumentOut, PostListResponse, TagOut } from "@/lib/types";

/** 标签页（FR-VIEW-07）：某标签下的全部文章与知识库文档。
 *
 * 文章与文档共用一套标签，首页「热门标签」的计数也是两者相加，
 * 所以这里必须两类都列出来 —— 否则计数会大于点进来看到的条数。
 */
export default async function TagPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [data, docs, tags] = await Promise.all([
    serverFetch<PostListResponse>(`/api/posts?tag=${slug}`),
    serverFetch<DocumentOut[]>(`/api/docs?tag=${slug}`),
    serverFetch<TagOut[]>("/api/tags"),
  ]);
  const tagName = tags.find((t) => t.slug === slug)?.name ?? slug;
  const total = data.items.length + docs.length;

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-semibold">标签：{tagName}</h1>
        <p className="mb-8 mt-1 text-sm text-faint">
          共 {total} 项（文章 {data.items.length} · 资料 {docs.length}）
        </p>

        {total === 0 && <p className="text-muted">该标签下暂无内容。</p>}

        {data.items.length > 0 && (
          <section className="mb-10">
            <h2 className="mb-4 text-sm font-medium text-faint">文章</h2>
            <ul className="space-y-6">
              {data.items.map((p) => (
                <li key={p.id} className="space-y-1">
                  <Link
                    href={`/posts/${p.slug}`}
                    className="text-lg font-medium hover:text-accent"
                  >
                    {p.title}
                  </Link>
                  {p.summary && <p className="text-sm text-muted">{p.summary}</p>}
                </li>
              ))}
            </ul>
          </section>
        )}

        {docs.length > 0 && (
          <section>
            <h2 className="mb-4 text-sm font-medium text-faint">知识库资料</h2>
            <ul className="space-y-6">
              {docs.map((d) => (
                <li key={d.id} className="space-y-1">
                  <Link href={`/docs/${d.id}`} className="text-lg font-medium hover:text-accent">
                    {d.title}
                  </Link>
                  <p className="text-xs text-faint">
                    {d.file_format} · {d.dir_path || "根目录"}
                  </p>
                  {d.description && <p className="text-sm text-muted">{d.description}</p>}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </main>
  );
}
